"""Load an external, reviewed event CSV into ``dw.dim_event`` idempotently."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

import psycopg

_ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ETL_DIR))

from common import connect, project_root  # noqa: E402

EVENT_TYPES = {"cap_nhat", "khuyen_mai", "mua_thi", "su_co"}
REQUIRED_COLUMNS = {
    "event_type",
    "start_date",
    "end_date",
    "description",
    "platform_name",
    "needs_review",
}


def _parse_bool(value: str, *, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "co", "có"} or "cần kiểm tra" in normalized:
        return True
    if normalized in {"false", "0", "no", "khong", "không"}:
        return False
    raise ValueError(f"Dòng {row_number}: needs_review phải là true hoặc false.")


def read_events(csv_path: Path) -> list[dict[str, object]]:
    """Read and validate the private event seed without connecting to PostgreSQL."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp sự kiện: {csv_path}")

    records: list[dict[str, object]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError("Thiếu cột trong CSV: " + ", ".join(sorted(missing)))

        for row_number, row in enumerate(reader, start=2):
            event_type = (row.get("event_type") or "").strip()
            description = (row.get("description") or "").strip()
            platform_name = (row.get("platform_name") or "").strip() or None
            start_value = (row.get("start_date") or "").strip()
            end_value = (row.get("end_date") or "").strip()
            if event_type not in EVENT_TYPES:
                raise ValueError(f"Dòng {row_number}: event_type không hợp lệ: {event_type!r}.")
            if not description:
                raise ValueError(f"Dòng {row_number}: description không được để trống.")
            try:
                start_date = date.fromisoformat(start_value)
                end_date = date.fromisoformat(end_value) if end_value else None
            except ValueError as exc:
                raise ValueError(f"Dòng {row_number}: ngày phải theo dạng YYYY-MM-DD.") from exc
            if end_date is not None and end_date < start_date:
                raise ValueError(f"Dòng {row_number}: end_date không được trước start_date.")

            records.append(
                {
                    "event_type": event_type,
                    "start_date": start_date,
                    "end_date": end_date,
                    "description": description,
                    "platform_name": platform_name,
                    "needs_review": _parse_bool(row.get("needs_review") or "", row_number=row_number),
                }
            )
    return records


def load_events(conn: psycopg.Connection, records: Iterable[dict[str, object]]) -> dict[str, int]:
    """Insert new events, or update the review flag of an existing matching event."""
    counts = {"inserted": 0, "updated": 0}
    with conn.cursor() as cur:
        # Serialize seed loads because dim_event has no natural-key constraint.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('eduvision:dw.dim_event:seed'))")
        cur.execute("SELECT platform_name, platform_key FROM dw.dim_platform")
        platform_keys = {name.casefold(): key for name, key in cur.fetchall()}

        for record in records:
            platform_name = record["platform_name"]
            platform_key = None
            if platform_name is not None:
                platform_key = platform_keys.get(str(platform_name).casefold())
                if platform_key is None:
                    raise ValueError(
                        f"Nền tảng {platform_name!r} chưa có trong dw.dim_platform; hãy chạy ETL chiều trước."
                    )

            cur.execute(
                """
                SELECT event_key, needs_review
                FROM dw.dim_event
                WHERE event_type = %s
                  AND start_date = %s
                  AND end_date IS NOT DISTINCT FROM %s
                  AND description = %s
                  AND platform_key IS NOT DISTINCT FROM %s
                ORDER BY event_key
                LIMIT 1
                FOR UPDATE
                """,
                (
                    record["event_type"],
                    record["start_date"],
                    record["end_date"],
                    record["description"],
                    platform_key,
                ),
            )
            existing = cur.fetchone()
            if existing:
                if existing[1] != record["needs_review"]:
                    cur.execute(
                        "UPDATE dw.dim_event SET needs_review = %s WHERE event_key = %s",
                        (record["needs_review"], existing[0]),
                    )
                    counts["updated"] += 1
                continue

            cur.execute(
                """
                INSERT INTO dw.dim_event
                    (event_type, start_date, end_date, description, platform_key, needs_review)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    record["event_type"],
                    record["start_date"],
                    record["end_date"],
                    record["description"],
                    platform_key,
                    record["needs_review"],
                ),
            )
            counts["inserted"] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Nạp CSV sự kiện đã rà vào dw.dim_event.")
    default_path = project_root() / "data" / "raw" / "dim_event_seed.csv"
    parser.add_argument("--csv", type=Path, default=default_path, help="CSV riêng, không đưa lên Git")
    args = parser.parse_args()

    records = read_events(args.csv)
    if not records:
        print("CSV không có sự kiện; không thay đổi CSDL.")
        return 0
    with connect() as conn:
        counts = load_events(conn, records)
    print(f"Đã nạp dim_event: thêm {counts['inserted']}, cập nhật needs_review {counts['updated']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
