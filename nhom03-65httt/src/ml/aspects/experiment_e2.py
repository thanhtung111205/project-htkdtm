"""Compare rating and M1 text-sentiment signals around reviewed events."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import psycopg

_ROOT = Path(__file__).resolve().parents[3]
_ETL_DIR = _ROOT / "src" / "etl"
sys.path.insert(0, str(_ETL_DIR))

from common import connect, project_root  # noqa: E402

MIN_DAILY_REVIEWS = 5
SENTIMENT_CHANGE_THRESHOLD = 10.0
RATING_CHANGE_THRESHOLD = 0.5
WINDOW_DAYS = 14
EMAIL_RE = re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?84|0)(?:[\s().-]?\d){8,11}(?!\w)")
URL_RE = re.compile(r"(?i)\bhttps?://\S+")


def _redact_private_text(value: str | None) -> str:
    text = value or ""
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)
    return URL_RE.sub("[url]", text)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _sentiment_index(rows: list[dict[str, Any]]) -> tuple[float | None, int]:
    labels = [
        row["sentiment_label"]
        for row in rows
        if row["sentiment_label"] in {"tich_cuc", "trung_tinh", "tieu_cuc"}
    ]
    if not labels:
        return None, 0
    positive = sum(label == "tich_cuc" for label in labels)
    negative = sum(label == "tieu_cuc" for label in labels)
    # Theo docs/kpi_bhi.md: (P - N) / T * 100; trung tính vẫn nằm trong T.
    return (positive - negative) / len(labels) * 100, len(labels)


def _daily_metrics(rows: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["review_date"]].append(row)
    result: dict[date, dict[str, Any]] = {}
    for day, day_rows in grouped.items():
        ratings = [float(row["rating"]) for row in day_rows if row["rating"] is not None]
        sentiment_index, sentiment_count = _sentiment_index(day_rows)
        result[day] = {
            "review_count": len(day_rows),
            "rating_count": len(ratings),
            "sentiment_count": sentiment_count,
            "avg_rating": _mean(ratings),
            "sentiment_index": sentiment_index,
        }
    return result


def _measure_event(
    event: dict[str, Any], platform: dict[str, Any], rows: list[dict[str, Any]], window_days: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start = event["start_date"]
    end = event["end_date"] or start
    pre_start = start - timedelta(days=window_days)
    post_start = end + timedelta(days=1)
    post_end = end + timedelta(days=window_days)
    pre_rows = [row for row in rows if pre_start <= row["review_date"] < start]
    post_rows = [row for row in rows if post_start <= row["review_date"] <= post_end]
    signal_rows = [row for row in rows if pre_start <= row["review_date"] <= post_end]

    pre_ratings = [float(row["rating"]) for row in pre_rows if row["rating"] is not None]
    post_ratings = [float(row["rating"]) for row in post_rows if row["rating"] is not None]
    pre_rating = _mean(pre_ratings)
    post_rating = _mean(post_ratings)
    pre_si, pre_sentiment_count = _sentiment_index(pre_rows)
    post_si, post_sentiment_count = _sentiment_index(post_rows)

    daily = _daily_metrics(signal_rows)
    rating_amplitudes: list[float] = []
    si_amplitudes: list[float] = []
    detected_at: date | None = None
    for day in sorted(daily):
        metrics = daily[day]
        if not (post_start <= day <= post_end):
            continue
        rating_value = metrics["avg_rating"]
        si_value = metrics["sentiment_index"]
        if metrics["rating_count"] >= MIN_DAILY_REVIEWS and pre_rating is not None and rating_value is not None:
            rating_amplitudes.append(abs(rating_value - pre_rating))
        if metrics["sentiment_count"] >= MIN_DAILY_REVIEWS and pre_si is not None and si_value is not None:
            si_amplitudes.append(abs(si_value - pre_si))
        rating_signal = (
            metrics["rating_count"] >= MIN_DAILY_REVIEWS and pre_rating is not None
            and rating_value is not None and abs(rating_value - pre_rating) >= RATING_CHANGE_THRESHOLD
        )
        si_signal = (
            metrics["sentiment_count"] >= MIN_DAILY_REVIEWS and pre_si is not None
            and si_value is not None and abs(si_value - pre_si) >= SENTIMENT_CHANGE_THRESHOLD
        )
        if detected_at is None and (rating_signal or si_signal):
            detected_at = day

    comparable = [
        row for row in signal_rows
        if row["rating"] is not None and row["sentiment_label"] in {"tich_cuc", "trung_tinh", "tieu_cuc"}
    ]
    mismatches = [
        row for row in comparable
        if (row["rating"] >= 4 and row["sentiment_label"] == "tieu_cuc")
        or (row["rating"] <= 2 and row["sentiment_label"] == "tich_cuc")
    ]
    result = {
        "model_name": event["model_name"],
        "event_key": event["event_key"],
        "event_type": event["event_type"],
        "event_start": start,
        "event_end": end,
        "event_warning": event["event_warning"],
        "platform_name": platform["platform_name"],
        "pre_reviews": len(pre_rows),
        "post_reviews": len(post_rows),
        "pre_sentiment_reviews": pre_sentiment_count,
        "post_sentiment_reviews": post_sentiment_count,
        "pre_avg_rating": pre_rating,
        "post_avg_rating": post_rating,
        "rating_change": (post_rating - pre_rating) if pre_rating is not None and post_rating is not None else None,
        "pre_sentiment_index": pre_si,
        "post_sentiment_index": post_si,
        "sentiment_index_change": (post_si - pre_si) if pre_si is not None and post_si is not None else None,
        "detection_lag_days": (detected_at - end).days if detected_at else None,
        "rating_amplitude": max(rating_amplitudes) if rating_amplitudes else None,
        "sentiment_index_amplitude": max(si_amplitudes) if si_amplitudes else None,
        "mismatch_count": len(mismatches),
        "comparable_count": len(comparable),
        "mismatch_rate_pct": (100 * len(mismatches) / len(comparable)) if comparable else None,
    }
    return result, mismatches[:5]


def run_e2(conn: psycopg.Connection, *, model_name: str = "M1_phobert", window_days: int = WINDOW_DAYS) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_key, event_type, start_date, end_date, platform_key, description, needs_review
            FROM dw.dim_event
            WHERE needs_review = false
               OR (needs_review = true
                   AND event_type = 'cap_nhat'
                   AND (description ILIKE '%ngay phat hanh thuc te chua xac minh%'
                        OR description ILIKE '%ngày phát hành thực tế chưa xác minh%'))
            ORDER BY start_date, event_key
            """
        )
        events = [
            {
                "event_key": row[0], "event_type": row[1], "start_date": row[2],
                "end_date": row[3], "platform_key": row[4], "description": row[5],
                "needs_review": row[6],
                "event_warning": (
                    "Dùng ngày công bố làm mốc thay thế; ngày phát hành/rollout thực tế chưa xác minh."
                    if row[6] else None
                ),
                "model_name": model_name,
            }
            for row in cur.fetchall()
        ]
        cur.execute("SELECT model_key FROM dw.dim_model WHERE model_name = %s ORDER BY model_key DESC LIMIT 1", (model_name,))
        model_row = cur.fetchone()
        if model_row is None:
            raise RuntimeError(f"Không tìm thấy model_name={model_name!r} trong dw.dim_model.")
        model_key = model_row[0]
        cur.execute("SELECT platform_key, platform_name FROM dw.dim_platform ORDER BY platform_name")
        platforms = [{"platform_key": row[0], "platform_name": row[1]} for row in cur.fetchall()]

        results: list[dict[str, Any]] = []
        mismatch_cases: list[dict[str, Any]] = []
        for event in events:
            targets = [p for p in platforms if p["platform_key"] == event["platform_key"]] if event["platform_key"] else platforms
            if event["platform_key"] is not None and not targets:
                continue
            effective_end = event["end_date"] or event["start_date"]
            lower_date = event["start_date"] - timedelta(days=window_days)
            upper_date = effective_end + timedelta(days=window_days)
            for platform in targets:
                cur.execute(
                    """
                    SELECT t.full_date, r.review_key, r.rating, c.text, scored.sentiment_label
                    FROM dw.fact_review r
                    JOIN dw.dim_time t ON t.time_key = r.time_key
                    JOIN clean.review_text c USING (review_key)
                    LEFT JOIN dw.fact_review_sentiment scored
                        ON scored.review_key = r.review_key AND scored.model_key = %s
                    WHERE r.platform_key = %s AND t.full_date BETWEEN %s AND %s
                    ORDER BY t.full_date, r.review_key
                    """,
                    (model_key, platform["platform_key"], lower_date, upper_date),
                )
                rows = [
                    {"review_date": row[0], "review_key": row[1], "rating": row[2], "text": row[3], "sentiment_label": row[4]}
                    for row in cur.fetchall()
                ]
                if not rows:
                    continue
                result, cases = _measure_event(event, platform, rows, window_days)
                results.append(result)
                mismatch_cases.extend(
                    {
                        "event_key": event["event_key"],
                        "platform_name": platform["platform_name"],
                        "review_key": row["review_key"],
                        "rating": row["rating"],
                        "sentiment_label": row["sentiment_label"],
                        "text": _redact_private_text(row["text"]),
                    }
                    for row in cases
                )
    return results, mismatch_cases


def write_outputs(results: list[dict[str, Any]], cases: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_fields = [
        "model_name", "event_key", "event_type", "event_start", "event_end", "event_warning", "platform_name",
        "pre_reviews", "post_reviews", "pre_sentiment_reviews", "post_sentiment_reviews",
        "pre_avg_rating", "post_avg_rating", "rating_change", "pre_sentiment_index", "post_sentiment_index",
        "sentiment_index_change", "detection_lag_days", "rating_amplitude", "sentiment_index_amplitude",
        "mismatch_count", "comparable_count", "mismatch_rate_pct",
    ]
    case_fields = ["event_key", "platform_name", "review_key", "rating", "sentiment_label", "text"]
    with (output_dir / "e2_results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=result_fields)
        writer.writeheader()
        writer.writerows(results)
    with (output_dir / "e2_mismatch_cases_private.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=case_fields)
        writer.writeheader()
        writer.writerows(cases)


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo E2 bằng nhãn cảm xúc M1 quanh các sự kiện trong dw.dim_event.")
    parser.add_argument("--model-name", default="M1_phobert", help="Tên model cảm xúc trong dw.dim_model; mặc định M1_phobert.")
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    parser.add_argument("--output-dir", type=Path, default=project_root() / "data" / "reports")
    args = parser.parse_args()
    if args.window_days < 1:
        parser.error("--window-days phải lớn hơn 0.")
    with connect() as conn:
        results, cases = run_e2(conn, model_name=args.model_name, window_days=args.window_days)
    write_outputs(results, cases, args.output_dir)
    print(f"E2: {len(results)} cặp sự kiện/nền tảng, {len(cases)} ca lệch pha mẫu; tệp đầu ra ở {args.output_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
