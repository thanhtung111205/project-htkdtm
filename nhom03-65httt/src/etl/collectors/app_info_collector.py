"""Thu thập thông tin ứng dụng (điểm công bố, số đánh giá tích lũy, phiên bản, ngày cập nhật) cho các nền tảng (T4).

Nguồn: iTunes Lookup API (Apple, công khai) cho App Store và thư viện google-play-scraper cho Google Play.
Mã ứng dụng đọc từ config/platforms.yml (play_id, ios_id). Mỗi lần chạy là một ảnh chụp tại ngày chạy; chạy lại
trong cùng ngày không sinh dòng trùng, chạy lại hôm sau nối thêm dòng mới để có lịch sử.

Ví dụ (từ thư mục gốc kho):
    python nhom03-65httt/src/etl/collectors/app_info_collector.py
    python nhom03-65httt/src/etl/collectors/app_info_collector.py --only "ELSA Speak"

Kết quả: <out>/app_info.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collector_utils import (  # noqa: E402
    DEFAULT_OUT, CollectorError, check_sleep, http_get, select_platforms, write_csv,
)

LOOKUP_URL = "https://itunes.apple.com/lookup"
FIELDS = [
    "snapshot_date", "product", "store", "app_id", "title", "developer", "installs", "real_installs", "score",
    "ratings", "reviews", "version", "released", "last_updated", "free", "offers_iap", "release_notes",
]


def trim(text: Any, limit: int = 500) -> str:
    return str(text or "")[:limit].replace("\n", " ").strip()


def timestamp_to_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).date().isoformat()
    return str(value)[:10]


def play_row(snapshot: str, product: str, app_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_date": snapshot, "product": product, "store": "google_play", "app_id": app_id,
        "title": data.get("title"), "developer": data.get("developer"), "installs": data.get("installs"),
        "real_installs": data.get("realInstalls"), "score": data.get("score"), "ratings": data.get("ratings"),
        "reviews": data.get("reviews"), "version": data.get("version"), "released": data.get("released"),
        "last_updated": timestamp_to_date(data.get("updated")), "free": data.get("free"),
        "offers_iap": data.get("offersIAP"), "release_notes": trim(data.get("recentChanges")),
    }


def ios_row(snapshot: str, product: str, app_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "snapshot_date": snapshot, "product": product, "store": "app_store_vn", "app_id": app_id,
        "title": data.get("trackName"), "developer": data.get("sellerName"), "installs": "", "real_installs": "",
        "score": data.get("averageUserRating"), "ratings": data.get("userRatingCount"), "reviews": "",
        "version": data.get("version"), "released": (data.get("releaseDate") or "")[:10],
        "last_updated": (data.get("currentVersionReleaseDate") or "")[:10], "free": data.get("price") == 0,
        "offers_iap": "", "release_notes": trim(data.get("releaseNotes")),
    }


def ios_lookup(ios_id: str) -> dict[str, Any]:
    raw = http_get(LOOKUP_URL, {"id": ios_id, "country": "vn"}, retries=3, base_delay=4.0)
    results = json.loads(raw.decode("utf-8")).get("results", [])
    return results[0] if results else {}


def play_lookup(play_id: str) -> dict[str, Any]:
    from google_play_scraper import app as play_app  # nạp muộn: chỉ cần khi chạy thật

    return play_app(play_id, lang="vi", country="vn")


def read_existing_keys(path: Path) -> set[tuple[str, str, str]]:
    if not path.is_file():
        return set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {(r["snapshot_date"], r["product"], r["store"]) for r in csv.DictReader(handle)}


def collect(platforms: list[dict[str, Any]], snapshot: str, sleep: float, lookup_play=play_lookup,
            lookup_ios=ios_lookup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for platform in platforms:
        product = platform["id"]
        print(f"== {product}")
        if platform.get("play_id"):
            try:
                rows.append(play_row(snapshot, product, platform["play_id"], lookup_play(platform["play_id"])))
            except Exception as exc:  # noqa: BLE001 - thư viện Google Play ném nhiều loại lỗi
                print(f"  Google Play lỗi: {type(exc).__name__}", file=sys.stderr)
        time.sleep(sleep)
        if platform.get("ios_id"):
            try:
                data = lookup_ios(str(platform["ios_id"]))
                if data:
                    rows.append(ios_row(snapshot, product, str(platform["ios_id"]), data))
                else:
                    print("  App Store: Lookup không trả kết quả", file=sys.stderr)
            except CollectorError as exc:
                print(f"  App Store lỗi: {exc}", file=sys.stderr)
        time.sleep(sleep)
    return rows


def merge_snapshot(path: Path, new_rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Nối dòng mới vào lịch sử, bỏ dòng đã có cùng (ngày chụp, nền tảng, kho). Trả về (thêm, bỏ qua)."""
    existing: list[dict[str, Any]] = []
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
    keys = {(r["snapshot_date"], r["product"], r["store"]) for r in existing}
    added = [r for r in new_rows if (r["snapshot_date"], r["product"], r["store"]) not in keys]
    write_csv(path, FIELDS, existing + added)
    return len(added), len(new_rows) - len(added)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Thu thập thông tin ứng dụng (ảnh chụp theo ngày).")
    parser.add_argument("--only", metavar="ID", help="Chỉ một nền tảng (ID khớp platforms.yml); mặc định tất cả")
    parser.add_argument("--sleep", type=float, default=2.0, help="Giây nghỉ giữa các lần gọi (tối thiểu 2)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT / "context", help="Thư mục lưu app_info.csv")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        check_sleep(args.sleep)
        platforms = select_platforms(args.only)
    except CollectorError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    rows = collect(platforms, date.today().isoformat(), args.sleep)
    added, skipped = merge_snapshot(args.out / "app_info.csv", rows)
    print(f"Đã thêm {added} dòng, bỏ qua {skipped} dòng đã có trong ngày -> {args.out / 'app_info.csv'}")
    return 0 if rows else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
