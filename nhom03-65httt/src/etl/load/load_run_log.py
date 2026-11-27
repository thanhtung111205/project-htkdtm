"""G22: ghi nhật ký chạy pipeline vào dw.etl_run_log (mỗi BƯỚC của mỗi LẦN CHẠY một dòng).

- write_steps: gọi từ run_pipeline.py sau mỗi vòng; ghi theo run_id nên chạy lại cùng run_id không sinh trùng.
- backfill từ data/logs/pipeline_runs.jsonl: nạp các vòng đã chạy trước khi có bảng (chạy lại nhiều lần vẫn đúng).

    python src/etl/load/load_run_log.py [--jsonl data/logs/pipeline_runs.jsonl] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import psycopg

_ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ETL_DIR))

from common import connect, project_root  # noqa: E402

STEPS = ("collect", "raw", "clean", "dw", "news", "platform_period", "score", "alert")
STATUSES = ("success", "partial", "failed", "dry_run")


def write_steps(conn: psycopg.Connection, run_id: str, steps: list[dict]) -> int:
    """Thay toàn bộ dòng của run_id bằng danh sách bước mới. Không commit. Trả về số dòng ghi."""
    for step in steps:
        if step["step"] not in STEPS or step["status"] not in STATUSES:
            raise ValueError(f"Bước hoặc trạng thái không hợp lệ: {step['step']}/{step['status']}")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM dw.etl_run_log WHERE run_id = %s", (run_id,))
        for step in steps:
            cur.execute(
                "INSERT INTO dw.etl_run_log (run_id, step, started_at, finished_at, status, input_name, "
                "rows_read, rows_inserted, rows_dropped, error_message) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (run_id, step["step"], step["started_at"], step.get("finished_at"), step["status"],
                 step.get("input_name"), step.get("rows_read"), step.get("rows_inserted"),
                 step.get("rows_dropped"), (step.get("error") or None) and str(step["error"])[:1000]),
            )
    return len(steps)


def steps_from_entry(entry: dict) -> list[dict]:
    """Suy ra các bước từ một bản ghi pipeline_runs.jsonl (dùng cho backfill vòng cũ)."""
    summary = entry.get("summary") or {}
    started = entry["started_at"]
    finished = entry.get("finished_at") or started
    status = entry.get("status", "failed")
    if status == "running":
        status = "failed"
    if status not in STATUSES:
        status = "failed"
    error = entry.get("error")
    steps = [{"step": "collect", "started_at": started, "finished_at": finished,
              "status": "dry_run" if status == "dry_run" else ("success" if not summary.get("collectors_failed") else "partial"),
              "rows_read": summary.get("collectors_total"), "rows_dropped": summary.get("collectors_failed")}]
    if "raw_read" in summary:
        steps.append({"step": "raw", "started_at": started, "finished_at": finished, "status": status,
                      "rows_read": summary.get("raw_read"), "rows_inserted": summary.get("raw_inserted")})
        steps.append({"step": "clean", "started_at": started, "finished_at": finished, "status": status,
                      "rows_inserted": summary.get("clean_inserted"), "rows_dropped": summary.get("clean_dropped_empty")})
        steps.append({"step": "dw", "started_at": started, "finished_at": finished, "status": status,
                      "rows_inserted": summary.get("fact_inserted"), "rows_read": summary.get("fact_total")})
    elif status == "failed":
        steps[0]["status"] = "failed"
        steps[0]["error"] = error
    return steps


def backfill(conn: psycopg.Connection, jsonl: Path) -> dict[str, int]:
    runs = steps_written = 0
    if not jsonl.is_file():
        return {"runs": 0, "steps": 0}
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            datetime.fromisoformat(entry["started_at"])
            run_id = entry["run_id"]
        except (ValueError, KeyError):
            continue
        steps_written += write_steps(conn, run_id, steps_from_entry(entry))
        runs += 1
    return {"runs": runs, "steps": steps_written}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nạp nhật ký pipeline_runs.jsonl vào dw.etl_run_log")
    parser.add_argument("--jsonl", type=Path, default=project_root() / "data" / "logs" / "pipeline_runs.jsonl")
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with connect(args.env_file) as conn:
        result = backfill(conn, args.jsonl)
        conn.rollback() if args.dry_run else conn.commit()
    print(f"Đã nạp {result['runs']} vòng, {result['steps']} dòng bước" + (" (dry-run, đã hoàn tác)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
