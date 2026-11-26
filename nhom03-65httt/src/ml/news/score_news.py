"""Filter and score news titles into ``dw.fact_news_sentiment``.

By default this uses a small Vietnamese keyword baseline. A project M1 scorer can
be supplied as ``package.module:function``; it must return a dict containing
``sentiment_score``, ``sentiment_label`` and ``confidence``.
"""

from __future__ import annotations

import argparse
import importlib
import os
import re
import sys
import unicodedata
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

_ROOT = Path(__file__).resolve().parents[3]
_ETL_DIR = _ROOT / "src" / "etl"
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ETL_DIR))

from common import connect, load_platforms  # noqa: E402

SCORER = Callable[[str], dict[str, Any]]
LABELS = {"tich_cuc", "trung_tinh", "tieu_cuc"}
POSITIVE_TERMS = (
    "rat tot", "tot hon", "tot nhat", "hay", "de su dung", "hai long", "tuyet voi",
    "hieu qua", "tien bo", "cai thien", "chinh xac", "nhanh", "huu ich", "dang tin cay",
    "than thien", "danh gia cao",
)
NEGATIVE_TERMS = (
    "te", "loi", "lag", "cham", "treo", "khong hoat dong", "that vong", "kho su dung",
    "khong chinh xac", "mat tien", "qua dat", "khong dang tin", "gian doan", "su co",
)
NEGATIONS = ("khong", "chua", "chang", "khong con")
NEUTRAL_LABEL = "trung_tinh"
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return " ".join("".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").split())


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def keyword_score(text: str) -> dict[str, Any]:
    """Return a transparent title-only baseline score; not a replacement for M1."""
    folded = _fold(text)
    positive_hits = [term for term in POSITIVE_TERMS if _contains_term(folded, term)]
    negative_hits = [term for term in NEGATIVE_TERMS if _contains_term(folded, term)]

    # Handle short negated praise such as "không tốt" and "chưa hài lòng".
    adjusted_positive: list[str] = []
    for term in positive_hits:
        if any(_contains_term(folded, f"{negation} {term}") for negation in NEGATIONS):
            negative_hits.append(term)
        else:
            adjusted_positive.append(term)

    total = len(adjusted_positive) + len(negative_hits)
    if total == 0:
        return {"sentiment_score": 0.0, "sentiment_label": NEUTRAL_LABEL, "confidence": 0.4}
    score = (len(adjusted_positive) - len(negative_hits)) / total
    label = "tich_cuc" if score > 0 else "tieu_cuc" if score < 0 else NEUTRAL_LABEL
    confidence = min(0.8, 0.5 + 0.1 * total)
    return {"sentiment_score": round(score, 3), "sentiment_label": label, "confidence": round(confidence, 3)}


def load_scorer(spec: str | None) -> SCORER:
    if not spec:
        return keyword_score
    module_name, separator, function_name = spec.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError("Scorer phải có dạng package.module:function.")
    function = getattr(importlib.import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(f"{spec} không trỏ tới một hàm có thể gọi.")
    return function


def _validate_prediction(prediction: dict[str, Any]) -> tuple[float, str, float]:
    try:
        score = float(prediction["sentiment_score"])
        confidence = float(prediction["confidence"])
        label = str(prediction["sentiment_label"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Scorer cần trả sentiment_score, sentiment_label và confidence.") from exc
    if not -1 <= score <= 1:
        raise ValueError(f"sentiment_score ngoài [-1, 1]: {score}")
    if not 0 <= confidence <= 1:
        raise ValueError(f"confidence ngoài [0, 1]: {confidence}")
    if label not in LABELS:
        raise ValueError(f"sentiment_label không hợp lệ: {label!r}")
    return score, label, confidence


def _platform_patterns(platforms: list[dict[str, Any]]) -> dict[str, re.Pattern[str]]:
    patterns: dict[str, re.Pattern[str]] = {}
    for platform in platforms:
        news_config = platform.get("news") or {}
        pattern = news_config.get("title_match") or re.escape(str(platform["id"]))
        try:
            patterns[str(platform["id"]).casefold()] = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Regex tiêu đề của {platform['id']} không hợp lệ: {pattern!r}") from exc
    return patterns


def relevant_title(title: str, pattern: re.Pattern[str]) -> bool:
    """Require an exact platform/product match; generic exam headlines are excluded."""
    return bool(title and pattern.search(title))


def _local_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(VIETNAM_TZ).date() if value.tzinfo else value.date()
    return value


def _ensure_time(cur: psycopg.Cursor[Any], event_date: date) -> int:
    time_key = int(event_date.strftime("%Y%m%d"))
    cur.execute(
        """
        INSERT INTO dw.dim_time (time_key, full_date, week, month, quarter, year)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (time_key) DO NOTHING
        """,
        (time_key, event_date, event_date.isocalendar().week, event_date.month,
         (event_date.month - 1) // 3 + 1, event_date.year),
    )
    return time_key


def score_articles(
    conn: psycopg.Connection,
    scorer: SCORER,
    *,
    model_name: str,
    model_version: str,
    trained_at: date | None = None,
) -> dict[str, int]:
    platforms = load_platforms()
    patterns = _platform_patterns(platforms)
    stats = {"read": 0, "kept": 0, "unrelated": 0, "missing_date": 0, "missing_dimension": 0, "scored": 0}

    with conn.cursor() as cur:
        cur.execute("SELECT platform_name, platform_key FROM dw.dim_platform")
        platform_keys = {name.casefold(): key for name, key in cur.fetchall()}
        cur.execute("SELECT source_name, source_key FROM dw.dim_source")
        source_keys = {name.casefold(): key for name, key in cur.fetchall()}

        cur.execute(
            """
            INSERT INTO dw.dim_model (model_name, model_version, trained_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (model_name, model_version) DO NOTHING
            """,
            (model_name, model_version, trained_at),
        )

        cur.execute(
            "SELECT article_id, platform_name, origin, title, published_at FROM clean.news_article"
        )
        articles = cur.fetchall()
        stats["read"] = len(articles)

        for article_id, platform_name, origin, title, published_at in articles:
            pattern = patterns.get(platform_name.casefold())
            if pattern is None or not relevant_title(title, pattern):
                stats["unrelated"] += 1
                continue
            stats["kept"] += 1
            event_date = _local_date(published_at)
            source_key = source_keys.get(str(origin or "").casefold())
            platform_key = platform_keys.get(platform_name.casefold())
            source_name = str(origin or "").strip()
            if source_name and source_key is None:
                cur.execute(
                    """
                    INSERT INTO dw.dim_source (source_name, source_type)
                    VALUES (%s, 'bao_chi')
                    ON CONFLICT (source_name) DO UPDATE SET source_type = EXCLUDED.source_type
                    RETURNING source_key
                    """,
                    (source_name,),
                )
                source_key = cur.fetchone()[0]
                source_keys[source_name.casefold()] = source_key
            if event_date is None or source_key is None or platform_key is None:
                stats["missing_date" if event_date is None else "missing_dimension"] += 1
                continue

            score, label, confidence = _validate_prediction(scorer(title))
            time_key = _ensure_time(cur, event_date)
            mention_count = max(1, len(pattern.findall(title)))
            cur.execute(
                """
                INSERT INTO dw.fact_news_sentiment
                    (source_key, article_id, platform_key, time_key, sentiment_score,
                     sentiment_label, confidence, mention_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_key, article_id, platform_key) DO UPDATE SET
                    time_key = EXCLUDED.time_key,
                    sentiment_score = EXCLUDED.sentiment_score,
                    sentiment_label = EXCLUDED.sentiment_label,
                    confidence = EXCLUDED.confidence,
                    mention_count = EXCLUDED.mention_count
                """,
                (source_key, article_id, platform_key, time_key, score, label, confidence, mention_count),
            )
            stats["scored"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Lọc và chấm cảm xúc tiêu đề báo chí vào dw.fact_news_sentiment.")
    parser.add_argument(
        "--scorer",
        default=os.environ.get("TA4_SCORER"),
        help="Hàm M1 dạng package.module:function; mặc định dùng baseline từ khóa có ghi nhãn.",
    )
    parser.add_argument(
        "--model-name",
        default=os.environ.get("TA4_MODEL_NAME"),
        help="Tên ghi vào dim_model (mặc định suy ra từ scorer).",
    )
    parser.add_argument("--model-version", default=os.environ.get("TA4_MODEL_VERSION", "v1"))
    parser.add_argument("--trained-at", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    scorer = load_scorer(args.scorer)
    default_name = "M1" if args.scorer else "TA4_lexicon_baseline"
    with connect() as conn:
        stats = score_articles(
            conn,
            scorer,
            model_name=args.model_name or default_name,
            model_version=args.model_version,
            trained_at=args.trained_at,
        )
    print(
        "Bài báo: "
        f"đọc {stats['read']}, giữ {stats['kept']}, loại không liên quan {stats['unrelated']}, "
        f"thiếu ngày/chiều {stats['missing_date'] + stats['missing_dimension']}, "
        f"đã chấm {stats['scored']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
