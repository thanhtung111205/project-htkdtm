"""Transparent keyword baseline for four Vietnamese learning-review aspects."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any

ASPECT_TERMS: dict[str, tuple[str, ...]] = {
    "Technical": (
        "ung dung", "app", "loi", "lag", "cham", "treo", "dang nhap", "tai bai",
        "giao dien", "am thanh", "micro", "ket noi", "crash", "khong mo duoc",
    ),
    "Academic": (
        "giang vien", "giao vien", "thay co", "bai giang", "khoa hoc", "bai tap",
        "noi dung", "hoc tap", "kien thuc", "lo trinh", "phat am", "tu vung", "ngu phap", "day hoc",
    ),
    "Customer Service": (
        "cham soc khach hang", "cskh", "ho tro", "tu van", "nhan vien", "hoan tien",
        "phan hoi", "lien he", "giai dap", "khieu nai", "khong ho tro", "khong hoan tien",
    ),
    "Pricing": (
        "phi", "tien hoc", "tien phi", "hoc phi", "thanh toan", "dang ky goi", "premium",
        "re", "goi hoc", "thu phi", "gia han", "huy goi", "mien phi", "gia cao", "gia qua cao",
        "gia dat", "gia ca", "gia tien", "gia re", "qua dat", "mac qua", "mac tien", "mac hon",
    ),
}
ASPECT_ORDER = tuple(ASPECT_TERMS)
POSITIVE_TERMS = (
    "hay", "rat tot", "tot hon", "tot nhat", "de hieu", "hai long", "tuyet voi", "huu ich", "tien bo", "nhanh",
    "chinh xac", "than thien", "on dinh", "re", "dang tien",
)
NEGATIVE_TERMS = (
    "te", "loi", "lag", "cham", "treo", "kho", "that vong", "khong hai long",
    "khong dung duoc", "khong dang nhap duoc", "gia cao", "gia qua cao", "gia dat", "qua dat",
    "mac qua", "mac tien", "mac hon", "mat tien", "phi cao", "khong chinh xac",
)
NEGATION_TERMS = ("khong", "chua", "chang", "khong the")
CLAUSE_SPLIT = re.compile(r"[,;.!?\n]+|\s+(?:nhung|tuy nhien|con|however|but)\s+", re.IGNORECASE)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    return " ".join("".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").split())


def _has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _sentiment(clause: str) -> tuple[float, int]:
    positives = [term for term in POSITIVE_TERMS if _has_phrase(clause, term)]
    if _has_phrase(clause, "tot") and not _has_phrase(clause, "tot nghiep"):
        positives.append("tot")
    negatives = [term for term in NEGATIVE_TERMS if _has_phrase(clause, term)]
    adjusted_positives: list[str] = []
    for term in positives:
        # "hay" trước một vấn đề diễn tả tần suất ("app hay bị lỗi"), không phải lời khen.
        if term == "hay" and any(
            _has_phrase(clause, f"hay {problem}")
            or _has_phrase(clause, f"hay bi {problem}")
            or _has_phrase(clause, f"hay gap {problem}")
            for problem in NEGATIVE_TERMS
        ):
            continue
        negated = any(_has_phrase(clause, f"{negation} {term}") for negation in NEGATION_TERMS)
        if negated:
            negatives.append(term)
        else:
            adjusted_positives.append(term)
    evidence_count = len(adjusted_positives) + len(negatives)
    if evidence_count == 0:
        return 0.0, 0
    return (len(adjusted_positives) - len(negatives)) / evidence_count, evidence_count


def predict_aspects(text: str) -> list[dict[str, Any]]:
    """Return aspects explicitly mentioned in text; never fabricate an aspect."""
    folded = _fold(text)
    by_aspect: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for clause in CLAUSE_SPLIT.split(folded):
        if not clause.strip():
            continue
        clause_aspects = [
            aspect for aspect, terms in ASPECT_TERMS.items()
            if any(_has_phrase(clause, term) for term in terms)
        ]
        if not clause_aspects:
            continue
        sentiment = _sentiment(clause)
        for aspect in clause_aspects:
            by_aspect[aspect].append(sentiment)

    results: list[dict[str, Any]] = []
    for aspect in ASPECT_ORDER:
        values = by_aspect.get(aspect)
        if not values:
            continue
        score = sum(value[0] for value in values) / len(values)
        evidence_count = sum(value[1] for value in values)
        label = "tich_cuc" if score > 0 else "tieu_cuc" if score < 0 else "trung_tinh"
        confidence = min(0.9, 0.55 + 0.1 * evidence_count) if evidence_count else 0.5
        results.append(
            {
                "aspect_name": aspect,
                "sentiment_label": label,
                "sentiment_score": round(score, 3),
                "confidence": round(confidence, 3),
            }
        )
    return results
