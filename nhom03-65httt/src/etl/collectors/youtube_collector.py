"""Thu thập bình luận YouTube về các nền tảng E-learning bằng YouTube Data API v3 chính thức (T4).

Khóa API lấy từ biến môi trường YOUTUBE_API_KEY hoặc tệp .env (xem .env.example); KHÔNG ghi vào mã. Khóa được gửi qua
tiêu đề HTTP, không nằm trong URL, nên không xuất hiện trong thông báo lỗi hay nhật ký.
Truy vấn tìm video đọc từ config/platforms.yml (mục `youtube_queries`); số bình luận tối đa mỗi video lấy từ
defaults.youtube.max_comments_per_video. Hạn mức YouTube mặc định 10.000 đơn vị mỗi ngày: một lần tìm tốn 100 đơn vị,
một trang bình luận tốn 1 đơn vị. Chịu YouTube API Services Terms of Service và Developer Policies.

Ví dụ (từ thư mục gốc kho):
    python nhom03-65httt/src/etl/collectors/youtube_collector.py --only "ELSA Speak" --per-query 3

Kết quả: <out>/youtube_<nen_tang>.csv với 12 cột chuẩn (source = youtube, không có số sao), và
<out>/youtube_videos_log.csv ghi video đã quét.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collector_utils import (  # noqa: E402
    DEFAULT_OUT, REVIEW_COLUMNS, CollectorError, author_hash, check_sleep, guess_lang, http_get, load_config,
    now_iso, read_env_value, select_platforms, slugify, write_csv,
)

API = "https://www.googleapis.com/youtube/v3"
QUOTA_SEARCH, QUOTA_COMMENTS = 100, 1


class QuotaExceeded(CollectorError):
    pass


class Quota:
    def __init__(self, budget: int, reserve: int) -> None:
        self.used, self.budget, self.reserve = 0, budget, reserve

    def can(self, cost: int) -> bool:
        return self.used + cost <= self.budget - self.reserve

    def spend(self, cost: int) -> None:
        self.used += cost


def api_get(endpoint: str, params: dict[str, Any], key: str) -> dict[str, Any]:
    """Gọi API, khóa qua tiêu đề. Lỗi hết hạn mức tách riêng để dừng sớm; không in URL hay khóa."""
    try:
        raw = http_get(f"{API}/{endpoint}", params, headers={"X-Goog-Api-Key": key}, retries=3, base_delay=4.0)
    except CollectorError as exc:
        if "HTTP 403" in str(exc):
            raise QuotaExceeded("YouTube từ chối (403): hết hạn mức, khóa sai hoặc bình luận bị tắt") from exc
        raise
    return json.loads(raw.decode("utf-8"))


def find_videos(queries: list[str], platform_id: str, per_query: int, key: str, quota: Quota,
                sleep: float) -> list[dict[str, str]]:
    videos: dict[str, dict[str, str]] = {}
    for query in queries:
        if not quota.can(QUOTA_SEARCH):
            print("Dừng tìm video: sắp hết hạn mức.", file=sys.stderr)
            break
        result = api_get("search", {"part": "snippet", "type": "video", "q": query, "maxResults": per_query,
                                    "relevanceLanguage": "vi", "regionCode": "VN"}, key)
        quota.spend(QUOTA_SEARCH)
        for item in result.get("items", []):
            video_id = (item.get("id") or {}).get("videoId")
            if video_id and video_id not in videos:
                videos[video_id] = {"platform": platform_id, "video_id": video_id,
                                    "title": (item.get("snippet") or {}).get("title", "")}
        print(f"[tìm] '{query}': {len(result.get('items', []))} video (hạn mức đã dùng {quota.used})")
        time.sleep(sleep)
    return list(videos.values())


def normalize_comment(item: dict[str, Any], product: str, crawled_at: str) -> dict[str, Any] | None:
    top = (item.get("snippet") or {}).get("topLevelComment") or {}
    snippet = top.get("snippet") or {}
    text = (snippet.get("textDisplay") or snippet.get("textOriginal") or "").strip()
    comment_id = top.get("id")
    if not comment_id or not text:
        return None
    return {
        "source": "youtube", "product": product, "review_id": comment_id,
        "author_hash": author_hash(snippet.get("authorDisplayName")), "rating": "", "text": text,
        "lang_guess": guess_lang(text), "created_at": snippet.get("publishedAt", ""),
        "app_version": "", "thumbs_up": snippet.get("likeCount", 0), "reply_text": "", "crawled_at": crawled_at,
    }


def comments_of(video_id: str, product: str, key: str, quota: Quota, sleep: float,
                max_per_video: int) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    token = None
    crawled_at = now_iso()
    while len(rows) < max_per_video:
        if not quota.can(QUOTA_COMMENTS):
            return rows, "het_han_muc"
        params: dict[str, Any] = {"part": "snippet", "videoId": video_id, "maxResults": 100, "order": "time",
                                  "textFormat": "plainText"}
        if token:
            params["pageToken"] = token
        try:
            page = api_get("commentThreads", params, key)
        except QuotaExceeded:
            # 403 khi quét bình luận thường là video tắt bình luận; hết hạn mức thật được nhận biết ở lần tìm sau
            return rows, "tat_binh_luan_hoac_het_han_muc"
        except CollectorError as exc:
            return rows, f"loi: {exc}"
        quota.spend(QUOTA_COMMENTS)
        for item in page.get("items", []):
            row = normalize_comment(item, product, crawled_at)
            if row:
                rows.append(row)
        token = page.get("nextPageToken")
        if not token:
            break
        time.sleep(sleep)
    return rows[:max_per_video], "ok"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    defaults = (load_config().get("defaults", {}) or {}).get("youtube", {}) or {}
    parser = argparse.ArgumentParser(description="Thu thập bình luận YouTube (API chính thức) cho các nền tảng.")
    parser.add_argument("--only", metavar="ID", help="Chỉ một nền tảng (ID khớp platforms.yml); mặc định tất cả")
    parser.add_argument("--per-query", type=int, default=5, help="Số video mỗi truy vấn tìm kiếm (mặc định 5)")
    parser.add_argument("--max-per-video", type=int, default=int(defaults.get("max_comments_per_video", 150)),
                        help="Số bình luận tối đa mỗi video")
    parser.add_argument("--quota-budget", type=int, default=10000, help="Hạn mức ngày ước tính (mặc định 10000)")
    parser.add_argument("--quota-reserve", type=int, default=300, help="Dừng khi hạn mức còn dưới mức này")
    parser.add_argument("--sleep", type=float, default=float(defaults.get("min_sleep_seconds", 2)),
                        help="Giây nghỉ giữa các lần gọi (tối thiểu 2)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Thư mục lưu CSV")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        check_sleep(args.sleep)
        platforms = select_platforms(args.only)
    except CollectorError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    key = read_env_value("YOUTUBE_API_KEY")
    if not key:
        print("Thiếu YOUTUBE_API_KEY: đặt trong biến môi trường hoặc tệp .env (xem .env.example). Dừng.",
              file=sys.stderr)
        return 3

    quota = Quota(args.quota_budget, args.quota_reserve)
    video_log: list[dict[str, Any]] = []
    total = 0
    try:
        for platform in platforms:
            queries = platform.get("youtube_queries") or []
            if not queries:
                continue
            print(f"== {platform['id']}")
            videos = find_videos(queries, platform["id"], args.per_query, key, quota, args.sleep)
            rows: list[dict[str, Any]] = []
            seen: set[str] = set()
            for video in videos:
                comments, status = comments_of(video["video_id"], platform["id"], key, quota, args.sleep,
                                               args.max_per_video)
                new = [c for c in comments if c["review_id"] not in seen]
                seen.update(c["review_id"] for c in new)
                rows += new
                video_log.append({**video, "comments": len(new), "status": status})
                print(f"  video {video['video_id']}: {len(new)} bình luận ({status})")
                time.sleep(args.sleep)
            path = args.out / f"youtube_{slugify(platform['id'])}.csv"
            write_csv(path, REVIEW_COLUMNS, rows)
            total += len(rows)
            print(f"  -> {len(rows)} bình luận ({path.name})")
    except QuotaExceeded as exc:
        print(f"Dừng: {exc}", file=sys.stderr)
    except CollectorError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    if video_log:
        write_csv(args.out / "youtube_videos_log.csv", ["platform", "video_id", "title", "comments", "status"], video_log)
    print(f"Tổng {total} bình luận; hạn mức ước tính đã dùng {quota.used}/{args.quota_budget}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
