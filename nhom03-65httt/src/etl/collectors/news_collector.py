"""Thu thập tin báo chí nhắc đến các nền tảng E-learning (T4).

Nguồn: (1) Google News RSS theo từ khóa, chia cửa sổ theo tháng; (2) RSS chuyên mục giáo dục của vài báo lớn,
lọc theo tên nền tảng. Từ khóa và mẫu lọc đọc từ config/platforms.yml (mục `news` của từng nền tảng).
Chỉ lưu tiêu đề, tên báo, đường dẫn, ngày đăng; KHÔNG lưu toàn văn (bản quyền).

Ví dụ (từ thư mục gốc kho):
    python nhom03-65httt/src/etl/collectors/news_collector.py --only DUOLINGO --since 2026-10-01
    python nhom03-65httt/src/etl/collectors/news_collector.py --probe     # kiểm tra từng nguồn có chạy không

Kết quả: <out>/news.csv và <out>/news_summary.csv (cột khớp data/raw/news/news.csv đã có).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collector_utils import (  # noqa: E402
    DEFAULT_OUT, CollectorError, check_sleep, http_get, load_config, now_iso, select_platforms, write_csv,
)

SITE_FEEDS = {
    "VnExpress Giáo dục": "https://vnexpress.net/rss/giao-duc.rss",
    "Tuổi Trẻ Giáo dục": "https://tuoitre.vn/rss/giao-duc.rss",
    "Dân trí Giáo dục": "https://dantri.com.vn/rss/giao-duc.rss",
    "Thanh Niên Giáo dục": "https://thanhnien.vn/rss/giao-duc.rss",
    "VietnamNet Giáo dục": "https://vietnamnet.vn/rss/giao-duc.rss",
}
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
FIELDS = ["platform", "origin", "title", "outlet", "link", "published_at", "collected_at", "title_hash"]


def parse_items(xml_bytes: bytes) -> Iterator[dict[str, str]]:
    root = ET.fromstring(xml_bytes)
    for item in root.iter("item"):
        published = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            published = ""
        source = item.find("source")
        yield {
            "title": html.unescape((item.findtext("title") or "").strip()),
            "link": (item.findtext("link") or "").strip(),
            "published_at": published,
            "outlet": source.text.strip() if source is not None and source.text else "",
        }


def clean_title(title: str, outlet: str) -> str:
    """Google News thêm ' - Tên báo' vào cuối tiêu đề."""
    if outlet and title.endswith(" - " + outlet):
        title = title[: -len(outlet) - 3]
    return title.strip()


def month_windows(since: date, until: date) -> Iterator[tuple[date, date]]:
    current = since.replace(day=1)
    while current <= until:
        following = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield current, following
        current = following


def title_hash(title: str) -> str:
    return hashlib.sha1(re.sub(r"\W+", "", title.lower()).encode("utf-8")).hexdigest()[:12]


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bỏ tin trùng theo (nền tảng, băm tiêu đề) và tin không có tiêu đề."""
    seen: set[tuple[str, str]] = set()
    result = []
    for row in rows:
        digest = title_hash(row["title"])
        key = (row["platform"], digest)
        if not row["title"] or key in seen:
            continue
        seen.add(key)
        result.append({**row, "title_hash": digest, "collected_at": row.get("collected_at") or now_iso()})
    return result


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_platform: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_platform[row["platform"]][row["published_at"][:7]] += 1
    out = []
    for platform, months in sorted(by_platform.items()):
        total = sum(months.values())
        verdict = "DAT (>=50 bai)" if total >= 50 else "MONG (10-49 bai)" if total >= 10 else "KHONG DU (<10 bai)"
        out.append({"platform": platform, "articles": total, "months_with_articles": len(months),
                    "oldest": min(months), "newest": max(months), "verdict": verdict})
    return out


def google_news(platform: dict[str, Any], since: date, until: date, sleep: float) -> list[dict[str, Any]]:
    keywords = (platform.get("news") or {}).get("keywords") or []
    rows: list[dict[str, Any]] = []
    for start, end in month_windows(since, until):
        for keyword in keywords:
            query = f"{keyword} after:{start.isoformat()} before:{end.isoformat()}"
            params = {"q": query, "hl": "vi", "gl": "VN", "ceid": "VN:vi"}
            try:
                items = list(parse_items(http_get(GOOGLE_NEWS_RSS, params, retries=2, base_delay=3.0)))
            except (CollectorError, ET.ParseError) as exc:
                print(f"  [Google News] {platform['id']} {start:%Y-%m}: LỖI {exc}", file=sys.stderr)
                items = []
            for item in items:
                item["title"] = clean_title(item["title"], item["outlet"])
                rows.append({**item, "platform": platform["id"], "origin": "google_news"})
            time.sleep(sleep)
        print(f"[Google News] {platform['id']} {start:%Y-%m}: tích lũy {len(rows)} tin")
    return rows


def site_rss(platforms: list[dict[str, Any]], sleep: float) -> list[dict[str, Any]]:
    patterns = {p["id"]: (p.get("news") or {}).get("title_match") for p in platforms}
    rows: list[dict[str, Any]] = []
    for name, url in SITE_FEEDS.items():
        try:
            items = list(parse_items(http_get(url, retries=1, base_delay=3.0)))
        except (CollectorError, ET.ParseError) as exc:
            print(f"[RSS] {name}: LỖI {exc}", file=sys.stderr)
            continue
        hits = 0
        for item in items:
            for platform_id, pattern in patterns.items():
                if pattern and re.search(pattern, item["title"], re.I):
                    rows.append({**item, "platform": platform_id, "origin": f"rss:{name}", "outlet": name})
                    hits += 1
        print(f"[RSS] {name}: {len(items)} tin, {hits} tin nhắc đến nền tảng")
        time.sleep(sleep)
    return rows


def probe() -> None:
    tests = {"Google News RSS": GOOGLE_NEWS_RSS + "?q=Duolingo&hl=vi&gl=VN&ceid=VN:vi", **SITE_FEEDS}
    for name, url in tests.items():
        try:
            items = list(parse_items(http_get(url, retries=1, base_delay=3.0)))
            newest = max((i["published_at"] for i in items if i["published_at"]), default="")
            print(f"OK   {name:22s} {len(items):4d} tin, mới nhất {newest[:10]}")
        except (CollectorError, ET.ParseError) as exc:
            print(f"LỖI  {name:22s} {exc}")
        time.sleep(2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    default_since = str((load_config().get("defaults", {}).get("news", {}) or {}).get("since", "2025-01-01"))
    parser = argparse.ArgumentParser(description="Thu thập tin báo chí về các nền tảng trong platforms.yml.")
    parser.add_argument("--only", metavar="ID", help="Chỉ một nền tảng (ID khớp platforms.yml); mặc định tất cả")
    parser.add_argument("--since", default=default_since, help=f"Ngày bắt đầu (mặc định {default_since})")
    parser.add_argument("--until", default=date.today().isoformat(), help="Ngày kết thúc (mặc định hôm nay)")
    parser.add_argument("--sleep", type=float, default=3.0, help="Giây nghỉ giữa các lần gọi (tối thiểu 2)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT / "news", help="Thư mục lưu CSV")
    parser.add_argument("--no-site-rss", action="store_true", help="Bỏ qua RSS chuyên mục của các báo")
    parser.add_argument("--probe", action="store_true", help="Chỉ kiểm tra từng nguồn có chạy được không")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        check_sleep(args.sleep)
        if args.probe:
            probe()
            return 0
        since, until = date.fromisoformat(args.since), date.fromisoformat(args.until)
        platforms = select_platforms(args.only)
    except (CollectorError, ValueError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2

    rows: list[dict[str, Any]] = []
    for platform in platforms:
        rows += google_news(platform, since, until, args.sleep)
    if not args.no_site_rss:
        rows += site_rss(platforms, args.sleep)
    rows = dedupe(rows)
    write_csv(args.out / "news.csv", FIELDS, rows)
    summary = summarize(rows)
    if summary:
        write_csv(args.out / "news_summary.csv", list(summary[0].keys()), summary)
    for item in summary:
        print(f"{item['platform']:13s} {item['articles']:4d} bài, {item['months_with_articles']:2d} tháng "
              f"{item['oldest']}→{item['newest']}  {item['verdict']}")
    print(f"Đã lưu {len(rows)} bài vào {args.out / 'news.csv'}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
