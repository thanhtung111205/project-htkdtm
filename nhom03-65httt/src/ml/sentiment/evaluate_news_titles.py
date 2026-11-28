"""Evaluate M1 on the manually labeled TA4 headline sample (never used for training)."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from phobert_model import Scorer
from sentiment_common import LABELS, ROOT

HERE = Path(__file__).resolve().parent
DEFAULT_LABELS = HERE / "fixtures" / "ta4_news_title_gold_50.csv"
DEFAULT_TITLES = ROOT / "data" / "raw" / "news" / "news.csv"
DEFAULT_MODEL_DIR = ROOT / "models" / "m1_phobert_sentiment"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_evaluation_rows(titles_path: Path, labels_path: Path) -> list[dict[str, str]]:
    articles: dict[str, dict[str, str]] = {}
    for article in _read_csv(titles_path):
        key = article.get("title_hash", "").strip()
        if not key:
            continue
        existing = articles.get(key)
        if existing and existing.get("title") != article.get("title"):
            raise ValueError(f"title_hash lặp nhưng tiêu đề khác nhau: {key}")
        articles[key] = article

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for label in _read_csv(labels_path):
        key = label.get("title_hash", "").strip()
        gold = label.get("sentiment_label", "").strip()
        if not key or key in seen:
            raise ValueError(f"title_hash rỗng hoặc bị lặp trong tập nhãn: {key!r}")
        if gold not in LABELS:
            raise ValueError(f"Nhãn không hợp lệ cho {key}: {gold!r}")
        article = articles.get(key)
        if article is None:
            raise ValueError(f"Không tìm thấy tiêu đề {key} trong {titles_path}")
        if article.get("platform", "").strip() != label.get("platform", "").strip():
            raise ValueError(f"Nền tảng không khớp cho tiêu đề {key}")
        rows.append({"title_hash": key, "text": article.get("title", ""), "gold": gold})
        seen.add(key)
    return rows


def _f1_by_label(gold: list[str], predicted: list[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for label in LABELS:
        tp = sum(actual == label and guess == label for actual, guess in zip(gold, predicted))
        fp = sum(actual != label and guess == label for actual, guess in zip(gold, predicted))
        fn = sum(actual == label and guess != label for actual, guess in zip(gold, predicted))
        denom = 2 * tp + fp + fn
        scores[label] = 2 * tp / denom if denom else 0.0
    return scores


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo M1 trên tập tiêu đề TA4 đã gán nhãn tay.")
    parser.add_argument("--titles", type=Path, default=DEFAULT_TITLES, help="CSV tiêu đề có cột title_hash, platform, title.")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS, help="CSV nhãn tay TA4.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--threads", type=int, default=16)
    args = parser.parse_args()

    rows = load_evaluation_rows(args.titles, args.labels)
    if not rows:
        raise ValueError("Tập đánh giá không có tiêu đề.")
    gold = [row["gold"] for row in rows]
    scorer = Scorer(args.model_dir, args.threads)
    probabilities = scorer.predict_proba([row["text"] for row in rows])
    predicted = [LABELS[int(index)] for index in probabilities.argmax(axis=1)]
    f1 = _f1_by_label(gold, predicted)
    accuracy = sum(actual == guess for actual, guess in zip(gold, predicted)) / len(gold)

    print(f"Số tiêu đề: {len(rows)} (chỉ kiểm định, không huấn luyện)")
    print("Phân bố nhãn tay:", dict(Counter(gold)))
    print(f"Accuracy: {accuracy:.3f}")
    print("F1 từng lớp:", {label: round(f1[label], 3) for label in LABELS})
    print(f"Macro-F1: {sum(f1.values()) / len(LABELS):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
