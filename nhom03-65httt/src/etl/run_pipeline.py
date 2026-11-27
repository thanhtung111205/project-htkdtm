"""Chạy trọn một vòng pipeline: thu thập đánh giá mới, nạp ETL, ghi nhật ký (T8a).

Ví dụ (chạy từ thư mục gốc nhom03-65httt):
    python src/etl/run_pipeline.py                      # một vòng đầy đủ cho 9 nền tảng
    python src/etl/run_pipeline.py --only "ELSA Speak" --count 20
    python src/etl/run_pipeline.py --skip-collect       # chỉ nạp các tệp đã thu thập trong thư mục incoming
    python src/etl/run_pipeline.py --report             # xem bằng chứng "tự chạy N ngày liên tiếp"

Mỗi vòng:
  1. Gọi collector Google Play và App Store cho từng nền tảng trong config/platforms.yml
     (giãn cách tối thiểu 2 giây, không đổi IP, không proxy: theo docs/dao_duc_phap_ly.md).
  2. Nạp các CSV vừa thu thập qua raw -> clean -> dw (loại trùng theo (source, review_id), chạy lại không sinh trùng).
  3. Sau khi nạp (trừ --dry-run và --no-post): chấm cảm xúc M1 cho đánh giá mới (nếu có mô hình và thư viện torch),
     rồi tổng hợp dw.fact_platform_period (nền tảng x tháng). Bước lỗi không làm hỏng vòng, trạng thái là `partial`.
  4. Với --with-context: thu thập thêm báo chí (nạp clean.news_article) và YouTube (khi có YOUTUBE_API_KEY).
  5. Ghi một bản ghi vào data/logs/pipeline_runs.jsonl (ngoài Git) và từng bước vào dw.etl_run_log (nếu bảng có).

Một collector lỗi không làm hỏng vòng: các nền tảng khác vẫn chạy, trạng thái vòng là `partial`.
Không sửa mã collector của người khác; chỉ gọi chúng qua dòng lệnh.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ETL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ETL_DIR))
sys.path.insert(0, str(ETL_DIR / "load"))

from common import connect, load_platforms, project_root  # noqa: E402
from load_clean import load_clean  # noqa: E402
from load_dw import load_dw  # noqa: E402
from load_news import load_news  # noqa: E402
from load_platform_period import build_platform_period  # noqa: E402
from load_raw import load_raw  # noqa: E402
from load_run_log import write_steps  # noqa: E402

VN_TZ = timezone(timedelta(hours=7))
COLLECTORS = ("google_play_collector.py", "app_store_collector.py")
LOCK_STALE_SECONDS = 3 * 3600
SCORE_SCRIPT = ETL_DIR.parent / "ml" / "sentiment" / "score_all.py"
MODEL_DIR = project_root() / "models" / "m1_phobert_sentiment"


# ---------------------------------------------------------------- nhật ký và khóa chạy
def log_path() -> Path:
    override = os.environ.get("EDUVISION_LOG_DIR")  # dùng cho kiểm thử, tránh ghi vào nhật ký thật
    path = Path(override) if override else project_root() / "data" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path / "pipeline_runs.jsonl"


def append_log(entry: dict) -> None:
    with log_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def read_log() -> list[dict]:
    path = log_path()
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def acquire_lock() -> Path | None:
    """Không cho hai vòng chạy chồng nhau. Khóa cũ hơn 3 giờ được coi là treo và bị bỏ qua."""
    lock = log_path().parent / "pipeline.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < LOCK_STALE_SECONDS:
        return None
    lock.write_text(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}", encoding="utf-8")
    return lock


# ---------------------------------------------------------------- báo cáo bằng chứng
def consecutive_days(entries: list[dict]) -> tuple[list[str], int]:
    """Các ngày (giờ Việt Nam) có ít nhất một vòng ETL thành công, và số ngày liên tiếp tính đến ngày gần nhất."""
    days = set()
    for entry in entries:
        if entry.get("status") in ("success", "partial") and not entry.get("dry_run"):
            started = datetime.fromisoformat(entry["started_at"]).astimezone(VN_TZ)
            days.add(started.date())
    ordered = sorted(days)
    if not ordered:
        return [], 0
    streak = 1
    for prev, cur in zip(reversed(ordered[:-1]), reversed(ordered[1:])):
        if (cur - prev).days == 1:
            streak += 1
        else:
            break
    return [d.isoformat() for d in ordered], streak


def print_report(min_days: int) -> int:
    entries = read_log()
    days, streak = consecutive_days(entries)
    print(f"Số vòng đã ghi: {len(entries)}")
    for entry in entries[-10:]:
        summary = entry.get("summary", {})
        print(
            f"  {entry['started_at'][:19]}  {entry['status']:<8} thu thập lỗi: "
            f"{summary.get('collectors_failed', '-')}/{summary.get('collectors_total', '-')}  "
            f"dòng mới ở raw: {summary.get('raw_inserted', '-')}"
        )
    print(f"Các ngày có vòng thành công: {', '.join(days) if days else '(chưa có)'}")
    print(f"Số ngày liên tiếp gần nhất: {streak} (yêu cầu tối thiểu {min_days})")
    print("ĐẠT" if streak >= min_days else "CHƯA ĐẠT: ghi số ngày thật vào báo cáo")
    return 0 if streak >= min_days else 3


def count_csv_rows(path: Path) -> int:
    """Số bản ghi (không tính dòng tiêu đề). Dùng bộ đọc CSV vì một đánh giá có thể xuống dòng trong ô văn bản."""
    csv.field_size_limit(10**9)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


# ---------------------------------------------------------------- thu thập
def run_collectors(platform_ids: list[str], out_dir: Path, count: int, sleep: float, timeout: int) -> list[dict]:
    results = []
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for platform_id in platform_ids:
        for script in COLLECTORS:
            started = time.monotonic()
            command = [
                sys.executable, str(ETL_DIR / "collectors" / script), "--only", platform_id,
                "--count", str(count), "--out", str(out_dir), "--sleep", str(sleep),
            ]
            item = {"collector": script.replace("_collector.py", ""), "platform": platform_id}
            try:
                done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=timeout, env=env)
                item["returncode"] = done.returncode
                if done.returncode != 0:
                    tail = (done.stderr or done.stdout or "").strip().splitlines()
                    item["error"] = tail[-1][:300] if tail else "không rõ lỗi"
            except subprocess.TimeoutExpired:
                item["returncode"] = -1
                item["error"] = f"quá {timeout} giây"
            item["seconds"] = round(time.monotonic() - started, 1)
            results.append(item)
            print(f"  thu thập {item['collector']:<10} {platform_id:<14} "
                  f"{'ok' if item['returncode'] == 0 else 'LỖI: ' + item.get('error', '')}")
            time.sleep(sleep)  # giãn cách giữa các lần gọi nguồn
    return results


# ---------------------------------------------------------------- bước sau ETL và dữ liệu bối cảnh (G21, G23)
def _step(steps: list[dict], name: str, status: str, started: datetime, **fields) -> None:
    steps.append({"step": name, "started_at": started.isoformat(), "status": status,
                  "finished_at": datetime.now(timezone.utc).isoformat(), **fields})


def run_post_steps(args: argparse.Namespace, steps: list[dict]) -> int:
    """Chấm M1 cho đánh giá mới rồi dựng lại fact_platform_period. Trả về số bước lỗi."""
    failures = 0
    scoring_ready = SCORE_SCRIPT.is_file() and MODEL_DIR.is_dir() and importlib.util.find_spec("torch") is not None
    if scoring_ready:
        started = datetime.now(timezone.utc)
        done = subprocess.run([sys.executable, str(SCORE_SCRIPT)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        if done.returncode == 0:
            _step(steps, "score", "success", started)
            print("  chấm cảm xúc M1: ok")
        else:
            failures += 1
            tail = (done.stderr or done.stdout or "").strip().splitlines()
            _step(steps, "score", "failed", started, error=tail[-1][:300] if tail else "không rõ lỗi")
            print("  chấm cảm xúc M1: LỖI")
    else:
        print("  bỏ qua chấm M1: chưa có mô hình hoặc thư viện torch trên máy này")
    started = datetime.now(timezone.utc)
    try:
        with connect(args.env_file) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('dw.fact_review_sentiment') IS NOT NULL AND "
                            "EXISTS (SELECT 1 FROM dw.fact_review_sentiment LIMIT 1)")
                has_model_labels = bool(cur.fetchone()[0])
            result = build_platform_period(conn, "model" if has_model_labels else "rating")
            conn.commit()
        _step(steps, "platform_period", "success", started, rows_inserted=result["rows_upserted"],
              rows_read=result["fact_review_total"])
        print(f"  tổng hợp nền tảng x tháng: {result['rows_upserted']} dòng ({result['sentiment_source']})")
    except Exception as exc:  # noqa: BLE001 - ghi lỗi vào nhật ký, không dừng vòng
        failures += 1
        _step(steps, "platform_period", "failed", started, error=f"{type(exc).__name__}: {exc}")
        print("  tổng hợp nền tảng x tháng: LỖI", exc, file=sys.stderr)
    return failures


def run_context(args: argparse.Namespace, platform_ids: list[str], steps: list[dict]) -> int:
    """Thu thập báo chí (nạp clean.news_article) và YouTube (chỉ khi có YOUTUBE_API_KEY). Trả về số bước lỗi."""
    failures = 0
    out_dir = args.incoming.parent / "context_incoming" / datetime.now(VN_TZ).strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    only = [arg for pid in platform_ids for arg in ("--only", pid)]

    started = datetime.now(timezone.utc)
    news_dir = out_dir / "news"
    command = [sys.executable, str(ETL_DIR / "collectors" / "news_collector.py"), *only,
               "--sleep", str(args.sleep), "--out", str(news_dir)]
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=args.timeout, env=env)
        if done.returncode != 0:
            tail = (done.stderr or done.stdout or "").strip().splitlines()
            raise RuntimeError(tail[-1][:300] if tail else "collector báo chí lỗi")
        news_csv = news_dir / "news.csv"
        with connect(args.env_file) as conn:
            stats = load_news(conn, news_csv)
            conn.commit()
        _step(steps, "news", "success", started, input_name=news_csv.name,
              rows_read=stats.get("read"), rows_inserted=stats.get("inserted"))
        print(f"  báo chí: {stats.get('inserted')} bài mới")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        _step(steps, "news", "failed", started, error=f"{type(exc).__name__}: {exc}")
        print("  báo chí: LỖI", exc, file=sys.stderr)

    if os.environ.get("YOUTUBE_API_KEY"):
        command = [sys.executable, str(ETL_DIR / "collectors" / "youtube_collector.py"), *only,
                   "--out", str(out_dir / "youtube")]
        try:
            done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=args.timeout, env=env)
            ok = done.returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
        print("  YouTube:", "ok" if ok else "LỖI")
        failures += 0 if ok else 1
    else:
        print("  bỏ qua YouTube: chưa đặt YOUTUBE_API_KEY")
    return failures


def save_run_steps(args: argparse.Namespace, run_id: str, steps: list[dict]) -> None:
    """Ghi các bước vào dw.etl_run_log. Thiếu bảng hoặc không nối được CSDL thì chỉ cảnh báo, nhật ký JSONL vẫn đủ."""
    try:
        with connect(args.env_file) as conn:
            write_steps(conn, run_id, steps)
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"Cảnh báo: chưa ghi được dw.etl_run_log ({type(exc).__name__}: {exc})", file=sys.stderr)


# ---------------------------------------------------------------- một vòng
def run_cycle(args: argparse.Namespace) -> int:
    all_ids = [p["id"] for p in load_platforms()]
    platform_ids = args.only or all_ids
    unknown = [p for p in platform_ids if p not in all_ids]
    if unknown:
        print(f"Nền tảng không có trong config/platforms.yml: {', '.join(unknown)}", file=sys.stderr)
        return 2

    lock = acquire_lock()
    if lock is None:
        print("Đang có vòng khác chạy (pipeline.lock còn mới). Bỏ qua vòng này.", file=sys.stderr)
        return 4

    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    entry: dict = {"run_id": uuid.uuid4().hex[:12], "started_at": started.isoformat(),
                   "dry_run": args.dry_run, "platforms": platform_ids, "count": args.count,
                   "status": "running"}
    summary: dict = {}
    steps: list[dict] = []
    try:
        stamp = datetime.now(VN_TZ).strftime("%Y%m%d_%H%M%S")
        out_dir = args.incoming / stamp
        if args.skip_collect:
            # chỉ nạp các tệp có sẵn: lấy mọi CSV trong thư mục incoming
            files = sorted(args.incoming.rglob("*.csv"))
            collector_results: list[dict] = []
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"Thu thập {len(platform_ids)} nền tảng, mỗi nền tảng tối đa {args.count} đánh giá mỗi kho:")
            collector_results = run_collectors(platform_ids, out_dir, args.count, args.sleep, args.timeout)
            files = sorted(out_dir.glob("*.csv"))
        failed = sum(1 for r in collector_results if r["returncode"] != 0)
        # collector thoát mã 0 nhưng CSV rỗng (ví dụ nguồn cấp RSS của Apple trả 0 mục): báo rõ, không im lặng
        csv_rows = {path.name: count_csv_rows(path) for path in files}
        empty_files = sorted(name for name, n in csv_rows.items() if n == 0)
        summary.update(collectors_total=len(collector_results), collectors_failed=failed,
                       csv_files=len(files), csv_rows=csv_rows, empty_csv=empty_files)
        if empty_files:
            print(f"Cảnh báo: {len(empty_files)} tệp CSV không có dòng nào (nguồn trả rỗng): {', '.join(empty_files)}")
        entry["collectors"] = collector_results

        if not args.skip_collect and collector_results and failed == len(collector_results):
            raise RuntimeError("Mọi collector đều lỗi: không có dữ liệu mới để nạp (kiểm tra mạng hoặc nguồn bị chặn)")

        _step(steps, "collect", "dry_run" if args.dry_run else ("partial" if failed else "success"), started,
              rows_read=len(collector_results), rows_dropped=failed)
        raw_inserted = raw_read = 0
        etl_started = datetime.now(timezone.utc)
        with connect(args.env_file) as conn:
            for path in files:
                stats = load_raw(conn, path)
                raw_read += stats["read"]
                raw_inserted += stats["inserted"]
            clean_stats = load_clean(conn)
            dw_stats = load_dw(conn)
            if args.dry_run:
                conn.rollback()
            else:
                conn.commit()
        summary.update(raw_read=raw_read, raw_inserted=raw_inserted, clean_inserted=clean_stats["inserted"],
                       clean_dropped_empty=clean_stats["dropped_empty"], fact_inserted=dw_stats["inserted"],
                       fact_total=dw_stats["fact_total"])
        etl_status = "dry_run" if args.dry_run else "success"
        _step(steps, "raw", etl_status, etl_started, rows_read=raw_read, rows_inserted=raw_inserted)
        _step(steps, "clean", etl_status, etl_started, rows_inserted=clean_stats["inserted"],
              rows_dropped=clean_stats["dropped_empty"])
        _step(steps, "dw", etl_status, etl_started, rows_read=dw_stats["fact_total"], rows_inserted=dw_stats["inserted"])
        extra_failures = 0
        if not args.dry_run:
            if not args.no_post:
                print("Bước sau ETL:")
                extra_failures += run_post_steps(args, steps)
            if args.with_context:
                print("Dữ liệu bối cảnh:")
                extra_failures += run_context(args, platform_ids, steps)
        summary["post_failures"] = extra_failures
        entry["status"] = "dry_run" if args.dry_run else ("partial" if failed or extra_failures else "success")
        entry["summary"] = summary
        code = 0
    except Exception as exc:  # ghi nhật ký rồi báo lỗi rõ ràng, không nuốt lỗi
        entry["status"] = "failed"
        entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["summary"] = summary
        print("LỖI:", entry["error"], file=sys.stderr)
        code = 1
    finally:
        entry["finished_at"] = datetime.now(timezone.utc).isoformat()
        entry["seconds"] = round(time.monotonic() - clock, 1)
        append_log(entry)
        if steps and not args.dry_run:   # vòng chạy thử không để lại dấu vết trong CSDL
            save_run_steps(args, entry["run_id"], steps)
        lock.unlink(missing_ok=True)

    print(f"Trạng thái: {entry['status']} ({entry['seconds']} giây). Tóm tắt: "
          f"{json.dumps(summary, ensure_ascii=False)}")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Một vòng pipeline: thu thập, ETL, ghi nhật ký")
    parser.add_argument("--only", action="append", metavar="ID",
                        help="Chỉ chạy nền tảng này (lặp lại được); mặc định tất cả nền tảng trong platforms.yml")
    parser.add_argument("--count", type=int, default=100, help="Số đánh giá mỗi nền tảng mỗi kho (mặc định 100)")
    parser.add_argument("--sleep", type=float, default=2.0, help="Giây nghỉ giữa các lần gọi nguồn (tối thiểu 2)")
    parser.add_argument("--timeout", type=int, default=900, help="Giây tối đa cho mỗi lần gọi collector")
    parser.add_argument("--incoming", type=Path, default=project_root() / "data" / "raw" / "incoming",
                        help="Thư mục chứa CSV thu thập theo từng vòng (ngoài Git)")
    parser.add_argument("--skip-collect", action="store_true", help="Không thu thập, chỉ nạp CSV có sẵn trong incoming")
    parser.add_argument("--dry-run", action="store_true", help="Chạy thử, hoàn tác ETL, vòng không tính vào bằng chứng")
    parser.add_argument("--env-file", type=Path, default=None, help="Tệp .env chứa POSTGRES_*")
    parser.add_argument("--no-post", action="store_true",
                        help="Không chấm M1 và không dựng fact_platform_period sau khi nạp")
    parser.add_argument("--with-context", action="store_true",
                        help="Thu thập thêm báo chí (và YouTube nếu có YOUTUBE_API_KEY) trong cùng vòng")
    parser.add_argument("--report", action="store_true", help="In bằng chứng tự chạy liên tiếp rồi thoát")
    parser.add_argument("--min-days", type=int, default=3, help="Số ngày liên tiếp tối thiểu khi --report (mặc định 3)")
    args = parser.parse_args(argv)

    if args.sleep < 2:
        parser.error("--sleep phải từ 2 giây trở lên (docs/dao_duc_phap_ly.md)")
    if args.count < 1:
        parser.error("--count phải lớn hơn 0")
    if args.report:
        return print_report(args.min_days)
    return run_cycle(args)


if __name__ == "__main__":
    raise SystemExit(main())
