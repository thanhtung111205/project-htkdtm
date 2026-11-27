"""G12: nạp mức quan tâm Google Trends theo tháng vào clean.trends_monthly (cần migration 0007).

Đọc data/raw/context/trends_monthly.csv do trends_collector.py (T4) tạo. Tệp có thể là chế độ mốc (có cột
interest_scaled_to_anchor) hoặc chế độ --solo (chỉ interest_self_scaled); cột thiếu thì ghi rỗng.
Google Trends lấy mẫu lại mỗi lần gọi nên lần nạp sau GHI ĐÈ số của cùng (tháng, nền tảng). Nền tảng không có trong
dw.dim_platform vẫn được nạp nhưng được liệt kê để kiểm tra. Hàm không commit.

    python src/etl/load/load_trends.py [--csv data/raw/context/trends_monthly.csv] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import psycopg

_ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ETL_DIR))

from common import connect, project_root  # noqa: E402

REQUIRED = {"month", "platform", "keyword", "interest_self_scaled", "is_partial"}


def _number(value: str | None) -> float | None:
    value = (value or "").strip()
    return float(value) if value else None


def _month(value: str) -> date:
    year, month = value.strip()[:7].split("-")
    return date(int(year), int(month), 1)


def read_trends(csv_path: Path) -> list[dict]:
    """Đọc và kiểm tra tệp trends; lỗi định dạng báo kèm số dòng. Trùng (tháng, nền tảng) thì dòng sau thắng."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp Google Trends: {csv_path}")
    rows: dict[tuple[date, str], dict] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Thiếu cột trong trends_monthly.csv: " + ", ".join(sorted(missing)))
        for line, row in enumerate(reader, start=2):
            platform = (row.get("platform") or "").strip()
            if not platform:
                raise ValueError(f"Dòng {line}: thiếu tên nền tảng")
            try:
                item = {
                    "month": _month(row["month"]),
                    "platform_name": platform,
                    "keyword": (row.get("keyword") or platform).strip(),
                    "interest_self_scaled": _number(row.get("interest_self_scaled")),
                    "interest_scaled_to_anchor": _number(row.get("interest_scaled_to_anchor")),
                    "is_partial": (row.get("is_partial") or "").strip().lower() in ("true", "1", "yes"),
                    "platform_group": (row.get("platform_group") or "").strip() or None,
                }
            except (ValueError, IndexError) as exc:
                raise ValueError(f"Dòng {line}: giá trị không hợp lệ ({exc})") from exc
            self_scaled = item["interest_self_scaled"]
            if self_scaled is not None and not 0 <= self_scaled <= 100:
                raise ValueError(f"Dòng {line}: interest_self_scaled ngoài 0 đến 100: {self_scaled}")
            rows[(item["month"], platform)] = item
    return list(rows.values())


def load_trends(conn: psycopg.Connection, rows: list[dict]) -> dict[str, object]:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('clean.trends_monthly') IS NOT NULL")
        if not cur.fetchone()[0]:
            raise RuntimeError("Chưa có bảng clean.trends_monthly: chạy migration 0007 trước.")
        cur.execute("SELECT platform_name FROM dw.dim_platform")
        known = {r[0] for r in cur.fetchall()}
        inserted = updated = 0
        for row in rows:
            cur.execute(
                """
                INSERT INTO clean.trends_monthly (month, platform_name, keyword, interest_self_scaled,
                                                  interest_scaled_to_anchor, is_partial, platform_group)
                VALUES (%(month)s, %(platform_name)s, %(keyword)s, %(interest_self_scaled)s,
                        %(interest_scaled_to_anchor)s, %(is_partial)s, %(platform_group)s)
                ON CONFLICT (month, platform_name) DO UPDATE SET
                    keyword = EXCLUDED.keyword,
                    interest_self_scaled = EXCLUDED.interest_self_scaled,
                    interest_scaled_to_anchor = EXCLUDED.interest_scaled_to_anchor,
                    is_partial = EXCLUDED.is_partial,
                    platform_group = EXCLUDED.platform_group,
                    loaded_at = now()
                RETURNING (xmax = 0)
                """,
                row,
            )
            if cur.fetchone()[0]:
                inserted += 1
            else:
                updated += 1
    unknown = sorted({r["platform_name"] for r in rows} - known)
    return {"read": len(rows), "inserted": inserted, "updated": updated, "unknown_platforms": unknown}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nạp Google Trends theo tháng vào clean.trends_monthly")
    parser.add_argument("--csv", type=Path, default=project_root() / "data" / "raw" / "context" / "trends_monthly.csv")
    parser.add_argument("--dry-run", action="store_true", help="Nạp thử rồi hoàn tác, không ghi")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rows = read_trends(args.csv)
    with connect() as conn:
        result = load_trends(conn, rows)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    print(f"Google Trends: đọc {result['read']} dòng, thêm {result['inserted']}, cập nhật {result['updated']}"
          + (" (dry-run, đã hoàn tác)" if args.dry_run else ""))
    if result["unknown_platforms"]:
        print("Nền tảng không có trong dw.dim_platform:", ", ".join(result["unknown_platforms"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
