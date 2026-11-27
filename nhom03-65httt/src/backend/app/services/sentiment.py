"""M1 cảm xúc 3 lớp cho API (T2): nạp mô hình một lần, dự đoán từng văn bản.

Thứ tự ưu tiên (M1_BACKEND=auto): PhoBERT đã tinh chỉnh (models/m1_phobert_sentiment, cần torch, transformers, underthesea),
không có thì mô hình nền TF-IDF + Logistic Regression (models/m1_tfidf_lr/model.joblib, cần scikit-learn).
Không có mô hình nào thì `get_model()` báo ModelUnavailable để API trả 503 kèm lý do.

Cách tiền xử lý PHẢI giống src/ml/sentiment/phobert_model.py (tách từ underthesea, độ dài tối đa 128) để kết quả API
khớp với nhãn đã chấm vào dw.fact_review_sentiment; tests/test_predict_sentiment.py so sánh hai bên khi máy có torch.
Ảnh Docker của API không chứa src/ml nên phần này viết lại gọn ở đây thay vì import.
"""

from __future__ import annotations

import importlib.util
import threading
from dataclasses import dataclass
from typing import Callable

from app.core.config import get_settings

LABELS = ["tieu_cuc", "trung_tinh", "tich_cuc"]  # cùng thứ tự với sentiment_common.LABELS
MAX_LEN = 128


class ModelUnavailable(RuntimeError):
    """Không nạp được mô hình M1 nào (thiếu tệp mô hình hoặc thư viện)."""


@dataclass
class SentimentModel:
    name: str  # M1_phobert hoặc M1_tfidf_lr
    predict_proba: Callable[[list[str]], list[list[float]]]


def _segment(text: str) -> str:
    from underthesea import word_tokenize

    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    try:
        return word_tokenize(cleaned, format="text")
    except Exception:  # noqa: BLE001 - văn bản lạ thì dùng nguyên văn, giống phobert_model.segment
        return cleaned


def _load_phobert(model_dir, threads: int) -> SentimentModel:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    if threads > 0:
        torch.set_num_threads(threads)
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), num_labels=3)
    model.eval()

    def predict(texts: list[str]) -> list[list[float]]:
        enc = tokenizer([_segment(t) for t in texts], padding=True, truncation=True, max_length=MAX_LEN,
                        return_tensors="pt")
        with torch.no_grad():
            return torch.softmax(model(**enc).logits, dim=-1).tolist()

    return SentimentModel("M1_phobert", predict)


def _load_tfidf(path) -> SentimentModel:
    import joblib

    bundle = joblib.load(path)
    model = bundle["model"]
    order = [list(model.classes_).index(i) for i in range(len(LABELS))]  # cột xác suất theo nhãn 0, 1, 2

    def predict(texts: list[str]) -> list[list[float]]:
        return [[float(row[j]) for j in order] for row in model.predict_proba(texts)]

    return SentimentModel("M1_tfidf_lr", predict)


def _has(*modules: str) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in modules)


def load_model() -> SentimentModel:
    settings = get_settings()
    backend = settings.m1_backend.strip().lower() or "auto"
    if backend not in ("auto", "phobert", "tfidf"):
        raise ModelUnavailable(f"M1_BACKEND không hợp lệ: {settings.m1_backend!r} (auto, phobert, tfidf)")
    reasons = []
    if backend in ("auto", "phobert"):
        model_dir = settings.resolve_model_path(settings.m1_model_dir, "m1_phobert_sentiment")
        if model_dir is None:
            reasons.append("không thấy thư mục mô hình PhoBERT")
        elif not _has("torch", "transformers", "underthesea"):
            reasons.append("thiếu thư viện torch, transformers hoặc underthesea")
        else:
            return _load_phobert(model_dir, settings.m1_threads)
    if backend in ("auto", "tfidf"):
        path = settings.resolve_model_path(settings.m1_baseline_path, "m1_tfidf_lr/model.joblib")
        if path is None:
            reasons.append("không thấy tệp mô hình TF-IDF")
        elif not _has("sklearn", "joblib"):
            reasons.append("thiếu thư viện scikit-learn hoặc joblib")
        else:
            return _load_tfidf(path)
    raise ModelUnavailable("; ".join(reasons))


_lock = threading.Lock()
_model: SentimentModel | None = None


def get_model() -> SentimentModel:
    """Nạp mô hình ở lần gọi đầu (vài giây với PhoBERT), các lần sau dùng lại. Lỗi nạp không được nhớ, lần sau thử lại."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = load_model()
    return _model


def warm_up() -> None:
    """Nạp mô hình sẵn (gọi ở luồng nền khi khởi động). Lỗi chỉ in ra, lần gọi API sau vẫn thử lại và trả 503 kèm lý do."""
    try:
        get_model().predict_proba(["khởi động"])  # chạy thử một câu để nạp cả bộ tách từ
    except Exception as exc:  # noqa: BLE001
        print(f"M1 chưa nạp được khi khởi động: {exc}")


def reset_model() -> None:
    """Dùng trong kiểm thử: bỏ mô hình đã nạp để đọc lại cấu hình."""
    global _model
    with _lock:
        _model = None


def predict(texts: list[str]) -> tuple[str, list[dict]]:
    model = get_model()
    out = []
    for probs in model.predict_proba(texts):
        best = max(range(len(LABELS)), key=lambda i: probs[i])
        out.append({"label": LABELS[best], "confidence": round(probs[best], 4),
                    "scores": {name: round(p, 4) for name, p in zip(LABELS, probs)}})
    return model.name, out
