"""Tiện ích dùng chung cho các collector YouTube, báo chí, Google Trends, thông tin ứng dụng (T4).

Quy tắc thu thập theo docs/dao_duc_phap_ly.md: chỉ dữ liệu công khai hoặc API chính thức, giãn cách tối thiểu
2 giây, thử lại có độ trễ tăng dần, dừng khi bị chặn (không đổi IP, không proxy, không giả trình duyệt),
chỉ lưu author_hash, khóa API chỉ lấy từ biến môi trường hoặc .env (không ghi vào mã, nhật ký hay thông báo lỗi).
"""

from __future__ import annotations

import csv
import hashlib
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
PLATFORMS_FILE = REPO_ROOT / "nhom03-65httt" / "config" / "platforms.yml"
DEFAULT_OUT = REPO_ROOT / "nhom03-65httt" / "data" / "raw"
USER_AGENT = "EduVisionBI-student-research/0.1 (hoc tap; khong thuong mai)"
MIN_SLEEP = 2.0
VIETNAMESE_DIACRITICS = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ")
RETRY_STATUS = (429, 500, 502, 503, 504)

# Cột chuẩn của đánh giá và bình luận (khớp collector Google Play, App Store và ETL)
REVIEW_COLUMNS = [
    "source", "product", "review_id", "author_hash", "rating", "text", "lang_guess",
    "created_at", "app_version", "thumbs_up", "reply_text", "crawled_at",
]


class CollectorError(RuntimeError):
    """Lỗi thu thập có thông báo rõ ràng, không chứa khóa API."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def author_hash(name: str | None) -> str:
    """12 ký tự đầu của SHA-256 tên hiển thị; không lưu tên, ảnh hay đường dẫn hồ sơ."""
    if not name:
        return ""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


def guess_lang(text: str) -> str:
    return "vi" if sum(ch in VIETNAMESE_DIACRITICS for ch in (text or "").lower()) >= 2 else "other"


def slugify(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def check_sleep(value: float, minimum: float = MIN_SLEEP) -> float:
    if value < minimum:
        raise CollectorError(f"--sleep phải từ {minimum:g} giây trở lên")
    return value


def load_config(path: Path = PLATFORMS_FILE) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def select_platforms(only: str | None, path: Path = PLATFORMS_FILE) -> list[dict[str, Any]]:
    platforms = [p for p in load_config(path).get("platforms", []) if isinstance(p, dict) and p.get("id")]
    if only:
        picked = [p for p in platforms if p["id"] == only]
        if not picked:
            raise CollectorError(f"Nền tảng {only!r} không có trong config/platforms.yml")
        return picked
    return platforms


def read_env_value(name: str, env_file: Path | None = None) -> str:
    """Giá trị từ biến môi trường, nếu không có thì từ tệp .env ở gốc nhóm. Không bao giờ in giá trị này."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    path = env_file or (REPO_ROOT / "nhom03-65httt" / ".env")
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, raw = line.split("=", 1)
                if key.strip() == name:
                    return raw.strip().strip('"').strip("'")
    return ""


def http_get(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None,
             retries: int = 4, base_delay: float = 4.0, timeout: int = 30) -> bytes:
    """GET có thử lại với độ trễ tăng dần khi gặp 429 hoặc 5xx. Lỗi ném ra không kèm URL đầy đủ (tránh lộ khóa)."""
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_STATUS and attempt < retries:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise CollectorError(f"HTTP {exc.code} từ {urllib.parse.urlsplit(url).netloc}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < retries:
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise CollectorError(f"Không kết nối được {urllib.parse.urlsplit(url).netloc} ({type(exc).__name__})") from exc
    raise CollectorError("Không lấy được dữ liệu")


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> int:
    """Ghi CSV UTF-8 có BOM (đè tệp). Trả về số dòng."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
