"""G2: nạp nhà phát triển và nhóm nội dung vào dw.dim_platform (cần migration 0006).

- developer: lấy từ ảnh chụp thông tin ứng dụng (data/raw/context/app_info.csv do app_info_collector tạo). Ưu tiên tên công ty
  trên App Store (đầy đủ hơn), không có thì dùng tên trên Google Play. Không tự đặt giá trị khi nguồn thiếu.
- category: nhóm nội dung do NHÓM phân loại (đề cương mục 7.2: học tổng hợp, ngoại ngữ), khai báo trong CATEGORIES bên dưới.
Chạy lại nhiều lần cho cùng kết quả; hàm không commit.

    python src/etl/load/load_platform_attributes.py [--csv data/raw/context/app_info.csv] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import psycopg

_ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ETL_DIR))

from common import connect, project_root  # noqa: E402

# Phân loại của nhóm. hoc_tong_hop: học nhiều môn hoặc công cụ học chung; ngoai_ngu: ứng dụng dạy ngoại ngữ.
CATEGORIES = {
    "ELSA Speak": "ngoai_ngu",
    "DUOLINGO": "ngoai_ngu",
    "Busuu": "ngoai_ngu",
    "Memrise": "ngoai_ngu",
    "MONKEY": "ngoai_ngu",
    "Quizlet": "hoc_tong_hop",
    "Khan Academy": "hoc_tong_hop",
    "VUIHOC": "hoc_tong_hop",
    "HOCMAI": "hoc_tong_hop",
}
STORE_PRIORITY = ("app_store_vn", "google_play")   # thứ tự ưu tiên khi chọn tên nhà phát triển


def read_developers(csv_path: Path) -> dict[str, str]:
    """Tên nhà phát triển theo từng nền tảng (khóa là tên nền tảng ở cột product), lấy theo thứ tự ưu tiên cửa hàng."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp thông tin ứng dụng: {csv_path}")
    csv.field_size_limit(10**9)
    by_product: dict[str, dict[str, str]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = {"product", "store", "developer"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Thiếu cột trong app_info.csv: " + ", ".join(sorted(missing)))
        for row in reader:
            product = (row.get("product") or "").strip()
            developer = (row.get("developer") or "").strip()
            if product and developer:
                by_product.setdefault(product, {})[(row.get("store") or "").strip()] = developer   # ảnh chụp sau ghi đè trước
    chosen: dict[str, str] = {}
    for product, stores in by_product.items():
        for store in STORE_PRIORITY:
            if stores.get(store):
                chosen[product] = stores[store]
                break
        else:
            chosen[product] = next(iter(stores.values()))
    return chosen


def update_platform_attributes(conn: psycopg.Connection, developers: dict[str, str],
                               categories: dict[str, str] = CATEGORIES) -> dict[str, object]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'dw' AND table_name = 'dim_platform' "
            "AND column_name IN ('developer', 'category')"
        )
        if cur.fetchone()[0] != 2:
            raise RuntimeError("dw.dim_platform chưa có cột developer, category: chạy migration 0006 trước.")
        cur.execute("SELECT platform_name FROM dw.dim_platform ORDER BY platform_name")
        known = [row[0] for row in cur.fetchall()]
        updated, without_developer, without_category = 0, [], []
        for name in known:
            developer = developers.get(name)
            category = categories.get(name)
            if developer is None:
                without_developer.append(name)
            if category is None:
                without_category.append(name)
            cur.execute(
                "UPDATE dw.dim_platform SET developer = coalesce(%s, developer), category = coalesce(%s, category) "
                "WHERE platform_name = %s",
                (developer, category, name),
            )
            updated += cur.rowcount
    return {"platforms": len(known), "updated": updated,
            "without_developer": without_developer, "without_category": without_category}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nạp nhà phát triển và nhóm nội dung vào dw.dim_platform")
    parser.add_argument("--csv", type=Path, default=project_root() / "data" / "raw" / "context" / "app_info.csv")
    parser.add_argument("--dry-run", action="store_true", help="Tính rồi hoàn tác, không ghi")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    developers = read_developers(args.csv)
    with connect() as conn:
        result = update_platform_attributes(conn, developers)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    print(f"Đã cập nhật {result['updated']}/{result['platforms']} nền tảng" + (" (dry-run, đã hoàn tác)" if args.dry_run else ""))
    if result["without_developer"]:
        print("Thiếu nhà phát triển (không có trong app_info.csv):", ", ".join(result["without_developer"]))
    if result["without_category"]:
        print("Thiếu nhóm nội dung (chưa khai báo trong CATEGORIES):", ", ".join(result["without_category"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
