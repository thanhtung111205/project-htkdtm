"""Kiểm thử POST /api/v1/predict/sentiment (T2): 422, 503, mô hình nền TF-IDF, PhoBERT và độ khớp với bộ chấm toàn kho.

Bài cần tệp mô hình (models/, ngoài Git) hoặc thư viện torch tự bỏ qua khi máy không có.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import sentiment

client = TestClient(app)
URL = "/api/v1/predict/sentiment"
POSITIVE = "Ứng dụng rất hay, học phát âm tiến bộ rõ rệt, giáo viên nhiệt tình"
NEGATIVE = "App lỗi liên tục, mất tiền mà không học được gì, rất thất vọng"


@pytest.fixture(autouse=True)
def fresh_model():
    sentiment.reset_model()
    yield
    sentiment.reset_model()


def _force(monkeypatch, backend: str, **paths):
    settings = get_settings()
    monkeypatch.setattr(settings, "m1_backend", backend)
    for name, value in paths.items():
        monkeypatch.setattr(settings, name, value)


def _model_path(relative: str) -> Path | None:
    settings = get_settings()
    return settings.resolve_model_path("", relative)


def _has(*modules: str) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in modules)


def test_validation_returns_422():
    assert client.post(URL, json={"text": ""}).status_code == 422
    assert client.post(URL, json={"text": "   "}).status_code == 422
    assert client.post(URL, json={"text": "a" * 5001}).status_code == 422
    assert client.post(URL, json={}).status_code == 422


def test_missing_model_returns_503_with_reason(monkeypatch):
    _force(monkeypatch, "tfidf", m1_baseline_path="khong_co/model.joblib")
    res = client.post(URL, json={"text": "tốt"})
    assert res.status_code == 503 and "TF-IDF" in res.json()["detail"]


def test_invalid_backend_returns_503(monkeypatch):
    _force(monkeypatch, "khong_hop_le")
    assert client.post(URL, json={"text": "tốt"}).status_code == 503


def _check_body(body: dict, model: str):
    assert body["model"] == model
    assert body["label"] in sentiment.LABELS
    assert set(body["scores"]) == set(sentiment.LABELS)
    assert abs(sum(body["scores"].values()) - 1) < 1e-3
    assert body["confidence"] == max(body["scores"].values())


@pytest.mark.skipif(_model_path("m1_tfidf_lr/model.joblib") is None or not _has("sklearn", "joblib"),
                    reason="Chưa có models/m1_tfidf_lr/model.joblib hoặc scikit-learn")
def test_tfidf_baseline(monkeypatch):
    _force(monkeypatch, "tfidf", m1_baseline_path="")
    pos, neg = client.post(URL, json={"text": POSITIVE}), client.post(URL, json={"text": NEGATIVE})
    assert pos.status_code == neg.status_code == 200
    _check_body(pos.json(), "M1_tfidf_lr")
    assert pos.json()["label"] == "tich_cuc" and neg.json()["label"] == "tieu_cuc"


PHOBERT_READY = _model_path("m1_phobert_sentiment") is not None and _has("torch", "transformers", "underthesea")


@pytest.mark.skipif(not PHOBERT_READY, reason="Chưa có models/m1_phobert_sentiment hoặc torch")
def test_phobert(monkeypatch):
    _force(monkeypatch, "auto", m1_model_dir="")
    pos, neg = client.post(URL, json={"text": POSITIVE}), client.post(URL, json={"text": NEGATIVE})
    assert pos.status_code == neg.status_code == 200
    _check_body(pos.json(), "M1_phobert")
    assert pos.json()["label"] == "tich_cuc" and neg.json()["label"] == "tieu_cuc"
    assert pos.json()["label_vi"] == "Tích cực"


@pytest.mark.skipif(not PHOBERT_READY, reason="Chưa có models/m1_phobert_sentiment hoặc torch")
def test_api_matches_batch_scorer(monkeypatch):
    """API phải cho cùng xác suất với bộ chấm toàn kho (src/ml/sentiment), tức là khớp nhãn trong dw.fact_review_sentiment."""
    _force(monkeypatch, "phobert", m1_model_dir="")
    ml_dir = Path(__file__).resolve().parents[2] / "ml" / "sentiment"
    sys.path.insert(0, str(ml_dir))
    try:
        from phobert_model import Scorer
    finally:
        sys.path.remove(str(ml_dir))
    texts = [POSITIVE, NEGATIVE, "tạm được, giao diện bình thường"]
    expected = Scorer(_model_path("m1_phobert_sentiment")).predict_proba(texts)
    for text, row in zip(texts, expected):
        scores = client.post(URL, json={"text": text}).json()["scores"]
        assert [scores[name] for name in sentiment.LABELS] == pytest.approx([float(v) for v in row], abs=1e-3)
