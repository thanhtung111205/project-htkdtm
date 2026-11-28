"""Small, dependency-free metric helpers for aspect-wise gold-set evaluation."""

from __future__ import annotations

from collections.abc import Iterable


def binary_f1(gold: Iterable[bool], predicted: Iterable[bool]) -> float:
    gold_values = list(gold)
    predicted_values = list(predicted)
    if len(gold_values) != len(predicted_values):
        raise ValueError("Nhãn thật và nhãn dự đoán phải có cùng số dòng.")
    true_positive = sum(actual and guess for actual, guess in zip(gold_values, predicted_values))
    false_positive = sum(not actual and guess for actual, guess in zip(gold_values, predicted_values))
    false_negative = sum(actual and not guess for actual, guess in zip(gold_values, predicted_values))
    denominator = 2 * true_positive + false_positive + false_negative
    return (2 * true_positive / denominator) if denominator else 0.0


def aspect_f1(
    gold: dict[str, set[str]], predicted: dict[str, set[str]], aspects: Iterable[str]
) -> dict[str, float]:
    """Compute binary presence F1 for each aspect over the same review IDs."""
    review_ids = sorted(set(gold) | set(predicted))
    result: dict[str, float] = {}
    for aspect in aspects:
        key = aspect.casefold()
        result[aspect] = binary_f1(
            (key in {value.casefold() for value in gold.get(review_id, set())} for review_id in review_ids),
            (key in {value.casefold() for value in predicted.get(review_id, set())} for review_id in review_ids),
        )
    return result


def macro_f1(per_aspect: dict[str, float]) -> float:
    return sum(per_aspect.values()) / len(per_aspect) if per_aspect else 0.0
