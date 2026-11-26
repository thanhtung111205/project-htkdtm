"""Score clean reviews by aspect and write results to ``dw.fact_review_aspect``."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

_ROOT = Path(__file__).resolve().parents[3]
_ETL_DIR = _ROOT / "src" / "etl"
sys.path.insert(0, str(_ROOT / "src" / "backend"))
sys.path.insert(0, str(_ETL_DIR))

from app.services.aspects_baseline import predict_aspects as keyword_baseline  # noqa: E402
from common import connect  # noqa: E402

Scorer = Callable[[str], list[dict[str, Any]]]
ASPECT_NAMES = {"technical", "academic", "customer service", "pricing", "other"}
SENTIMENT_LABELS = {"tich_cuc", "trung_tinh", "tieu_cuc"}


def load_scorer(spec: str | None) -> Scorer:
    if not spec:
        return keyword_baseline
    module_name, separator, function_name = spec.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError("Scorer phải có dạng package.module:function.")
    function = getattr(importlib.import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(f"{spec} không trỏ tới một hàm có thể gọi.")
    return function


def _validate_predictions(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in predictions:
        try:
            name = str(item["aspect_name"])
            label = str(item["sentiment_label"])
            score = float(item["sentiment_score"])
            confidence = float(item["confidence"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Scorer cần trả aspect_name, sentiment_label, sentiment_score, confidence.") from exc
        normalized_name = name.casefold()
        if normalized_name not in ASPECT_NAMES:
            raise ValueError(f"aspect_name không hợp lệ: {name!r}")
        if normalized_name in seen:
            raise ValueError(f"Scorer trả lặp khía cạnh: {name!r}")
        if label not in SENTIMENT_LABELS:
            raise ValueError(f"sentiment_label không hợp lệ: {label!r}")
        if not -1 <= score <= 1 or not 0 <= confidence <= 1:
            raise ValueError("sentiment_score phải trong [-1, 1], confidence trong [0, 1].")
        seen.add(normalized_name)
        clean.append(
            {
                "aspect_name": name,
                "sentiment_label": label,
                "sentiment_score": score,
                "confidence": confidence,
            }
        )
    return clean


def score_reviews(
    conn: psycopg.Connection,
    scorer: Scorer,
    *,
    model_name: str,
    model_version: str,
    trained_at: date | None = None,
    replace_existing: bool = False,
) -> dict[str, int]:
    stats = {"reviews_read": 0, "reviews_with_aspects": 0, "aspect_rows_written": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT aspect_name, aspect_key FROM dw.dim_aspect")
        aspect_keys = {name.casefold(): key for name, key in cur.fetchall()}
        missing = {"technical", "academic", "customer service", "pricing"} - set(aspect_keys)
        if missing:
            raise RuntimeError("Thiếu khía cạnh trong dw.dim_aspect: " + ", ".join(sorted(missing)))

        cur.execute(
            """
            INSERT INTO dw.dim_model (model_name, model_version, trained_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (model_name, model_version) DO UPDATE
                SET trained_at = coalesce(EXCLUDED.trained_at, dw.dim_model.trained_at)
            RETURNING model_key
            """,
            (model_name, model_version, trained_at),
        )
        model_key = cur.fetchone()[0]
        cur.execute(
            """
            SELECT c.review_key, c.text, f.time_key, f.platform_key
            FROM clean.review_text c
            JOIN dw.fact_review f USING (review_key)
            WHERE c.text IS NOT NULL AND btrim(c.text) <> ''
            ORDER BY c.review_key
            """
        )
        reviews = cur.fetchall()
        stats["reviews_read"] = len(reviews)

        for review_key, text, time_key, platform_key in reviews:
            predictions = _validate_predictions(scorer(text))
            if replace_existing:
                cur.execute("DELETE FROM dw.fact_review_aspect WHERE review_key = %s", (review_key,))
            if predictions:
                stats["reviews_with_aspects"] += 1
            for item in predictions:
                aspect_key = aspect_keys[item["aspect_name"].casefold()]
                cur.execute(
                    """
                    INSERT INTO dw.fact_review_aspect AS existing
                        (review_key, aspect_key, time_key, platform_key, model_key,
                         sentiment_label, sentiment_score, confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (review_key, aspect_key) DO UPDATE SET
                        time_key = EXCLUDED.time_key,
                        platform_key = EXCLUDED.platform_key,
                        model_key = EXCLUDED.model_key,
                        sentiment_label = EXCLUDED.sentiment_label,
                        sentiment_score = EXCLUDED.sentiment_score,
                        confidence = EXCLUDED.confidence
                    WHERE existing.model_key = EXCLUDED.model_key
                    """,
                    (
                        review_key,
                        aspect_key,
                        time_key,
                        platform_key,
                        model_key,
                        item["sentiment_label"],
                        item["sentiment_score"],
                        item["confidence"],
                    ),
                )
                stats["aspect_rows_written"] += cur.rowcount
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Chấm cảm xúc theo khía cạnh vào dw.fact_review_aspect.")
    parser.add_argument("--scorer", help="Hàm M2 dạng package.module:function; mặc định dùng baseline từ khóa.")
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--model-version", default="v1")
    parser.add_argument("--trained-at", type=date.fromisoformat, default=None)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Xóa kết quả khía cạnh cũ của từng đánh giá trước khi ghi kết quả hiện tại.",
    )
    args = parser.parse_args()
    scorer = load_scorer(args.scorer)
    model_name = args.model_name or ("M2" if args.scorer else "TA3_keyword_baseline")
    with connect() as conn:
        stats = score_reviews(
            conn,
            scorer,
            model_name=model_name,
            model_version=args.model_version,
            trained_at=args.trained_at,
            replace_existing=args.replace_existing,
        )
    print(
        f"Đã đọc {stats['reviews_read']} đánh giá, có khía cạnh ở {stats['reviews_with_aspects']} đánh giá, "
        f"ghi {stats['aspect_rows_written']} dòng fact_review_aspect."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
