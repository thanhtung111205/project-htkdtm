"""Thu thập mức quan tâm theo tháng trên Google Trends cho các nền tảng (T4).

Dùng thư viện pytrends (KHÔNG chính thức, dễ bị giới hạn 429): chạy ít lần, chờ lùi dần khi bị chặn và DỪNG khi vẫn
bị chặn, không đổi IP, không proxy (docs/dao_duc_phap_ly.md). Từ khóa đọc từ config/platforms.yml (`trends_keyword`).
Chế độ mặc định so các nền tảng với một nền tảng mốc (Duolingo) trong cùng yêu cầu rồi quy về một thang; chế độ --solo
chuẩn hóa 0 đến 100 riêng cho từng từ khóa.

Ví dụ (từ thư mục gốc kho):
    python nhom03-65httt/src/etl/collectors/trends_collector.py --since 2019-01-01
    python nhom03-65httt/src/etl/collectors/trends_collector.py --solo --only "ELSA Speak"

Kết quả: <out>/trends_monthly.csv. Tháng cuối có is_partial = True là tháng chưa kết thúc, nên bỏ khi huấn luyện.
Cần: pip install pytrends pandas
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collector_utils import DEFAULT_OUT, CollectorError, check_sleep, select_platforms, write_csv  # noqa: E402

ANCHOR = "DUOLINGO"
MIN_TRENDS_SLEEP = 15.0
FIELDS = ["month", "platform", "keyword", "interest_scaled_to_anchor", "interest_self_scaled",
          "is_partial", "platform_group"]


def rescale_batches(frames: list[dict[str, list[float]]], anchor_keyword: str) -> dict[str, list[float]]:
    """frames: danh sách {từ khóa: chuỗi giá trị} cùng độ dài; mỗi batch có anchor_keyword.
    Quy mọi batch về thang của batch đầu theo tổng giá trị của mốc; mốc chỉ lấy từ batch đầu."""
    base_sum = float(sum(frames[0][anchor_keyword]))
    out: dict[str, list[float]] = {}
    for index, frame in enumerate(frames):
        anchor_sum = float(sum(frame[anchor_keyword]))
        factor = base_sum / anchor_sum if index > 0 and anchor_sum > 0 else 1.0
        for keyword, values in frame.items():
            if index > 0 and keyword == anchor_keyword:
                continue
            out[keyword] = [float(v) * factor for v in values]
    return out


def to_monthly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mỗi (nền tảng, tháng) đúng một dòng. Trends chỉ trả dữ liệu theo tháng khi khoảng thời gian dài hơn 5 năm;
    ngắn hơn thì trả theo tuần, nên gộp các tuần cùng tháng bằng trung bình. is_partial = True nếu có tuần chưa đủ."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["platform"], row["month"]), []).append(row)
    merged = []
    for (_platform, _month), items in groups.items():
        row = dict(items[0])
        for field in ("interest_scaled_to_anchor", "interest_self_scaled"):
            values = [float(i[field]) for i in items if i.get(field) not in (None, "")]
            if values:
                mean = sum(values) / len(values)
                row[field] = round(mean, 2) if field == "interest_scaled_to_anchor" else round(mean)
        row["is_partial"] = any(bool(i.get("is_partial")) for i in items)
        merged.append(row)
    return merged


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def fetch_trends(pytrends: Any, keywords: list[str], timeframe: str, geo: str, tries: int = 4) -> Any:
    """Gọi interest_over_time; bị 429 thì chờ lùi dần, hết số lần thử thì dừng (không vượt chặn)."""
    wait = 60.0
    for attempt in range(1, tries + 1):
        try:
            pytrends.build_payload(keywords, timeframe=timeframe, geo=geo)
            frame = pytrends.interest_over_time()
            if frame is None or frame.empty:
                raise CollectorError("Google Trends trả về bảng rỗng")
            return frame
        except Exception as exc:  # noqa: BLE001 - pytrends ném nhiều loại lỗi
            print(f"   lỗi lần {attempt}/{tries}: {type(exc).__name__}", file=sys.stderr)
            if attempt == tries:
                raise CollectorError("Google Trends tiếp tục từ chối, dừng (không vượt giới hạn)") from exc
            print(f"   chờ {wait:g} giây rồi thử lại", file=sys.stderr)
            time.sleep(wait)
            wait *= 2
    raise CollectorError("Không lấy được Google Trends")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Thu thập Google Trends theo tháng cho các nền tảng.")
    parser.add_argument("--only", metavar="ID", help="Chỉ một nền tảng (ID khớp platforms.yml); cần --solo")
    parser.add_argument("--since", default="2019-01-01", help="Ngày bắt đầu (mặc định 2019-01-01)")
    parser.add_argument("--geo", default="VN", help="Mã quốc gia (mặc định VN)")
    parser.add_argument("--solo", action="store_true", help="Mỗi từ khóa một yêu cầu, chuẩn hóa 0 đến 100 riêng")
    parser.add_argument("--sleep", type=float, default=MIN_TRENDS_SLEEP,
                        help=f"Giây nghỉ giữa các yêu cầu (tối thiểu {MIN_TRENDS_SLEEP:g})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT / "context", help="Thư mục lưu trends_monthly.csv")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        check_sleep(args.sleep, MIN_TRENDS_SLEEP)
        if args.only and not args.solo:
            raise CollectorError("--only chỉ dùng cùng --solo (chế độ so với mốc cần đủ các nền tảng)")
        platforms = select_platforms(args.only)
    except CollectorError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2

    from pytrends.request import TrendReq  # nạp muộn: chỉ cần khi chạy thật

    pytrends = TrendReq(hl="vi-VN", tz=-420, timeout=(10, 40))
    timeframe = f"{args.since} {date.today().isoformat()}"
    by_keyword = {p.get("trends_keyword") or p["id"]: p for p in platforms}
    group_of = {p["id"]: p.get("platform_group", "quoc_te") for p in platforms}
    rows: list[dict[str, Any]] = []
    try:
        if args.solo:
            for keyword, platform in by_keyword.items():
                print(f" - {keyword}")
                frame = fetch_trends(pytrends, [keyword], timeframe, args.geo)
                partial = frame["isPartial"] if "isPartial" in frame else None
                for stamp, value in frame[keyword].items():
                    rows.append({"month": stamp.strftime("%Y-%m"), "platform": platform["id"], "keyword": keyword,
                                 "interest_self_scaled": int(value),
                                 "is_partial": bool(partial.loc[stamp]) if partial is not None else False,
                                 "platform_group": group_of[platform["id"]]})
                time.sleep(args.sleep)
        else:
            anchor_keyword = next((k for k, p in by_keyword.items() if p["id"] == ANCHOR), None)
            if anchor_keyword is None:
                raise CollectorError(f"Không có nền tảng mốc {ANCHOR} trong platforms.yml")
            others = [k for k in by_keyword if k != anchor_keyword]
            frames = []
            partial_flags = None
            for batch in chunked(others, 4):
                keywords = [anchor_keyword] + batch
                print(f" - {keywords}")
                frame = fetch_trends(pytrends, keywords, timeframe, args.geo)
                if partial_flags is None and "isPartial" in frame:
                    partial_flags = frame["isPartial"]
                frames.append({k: [float(v) for v in frame[k].tolist()] for k in keywords})
                index = frame.index
                time.sleep(args.sleep)
            scaled = rescale_batches(frames, anchor_keyword)
            for keyword, values in scaled.items():
                platform = by_keyword[keyword]
                for position, stamp in enumerate(index):
                    rows.append({"month": stamp.strftime("%Y-%m"), "platform": platform["id"], "keyword": keyword,
                                 "interest_scaled_to_anchor": round(values[position], 2),
                                 "is_partial": bool(partial_flags.iloc[position]) if partial_flags is not None else False,
                                 "platform_group": group_of[platform["id"]]})
    except CollectorError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        if not rows:
            return 1
    path = args.out / "trends_monthly.csv"
    rows = to_monthly(rows)
    write_csv(path, FIELDS, rows)
    print(f"Đã ghi {len(rows)} dòng -> {path}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
