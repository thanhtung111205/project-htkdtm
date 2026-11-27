"""Kiểm thử GET /api/v1/forecast (N2): 200, 404, 422, 503. Các bài cần dữ liệu tự bỏ qua nếu fact_forecast còn trống."""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def test_validation_returns_422():
    assert client.get("/api/v1/forecast").status_code == 422
    assert client.get("/api/v1/forecast?platform=ELSA&periods=0").status_code == 422
    assert client.get("/api/v1/forecast?platform=ELSA&periods=x").status_code == 422
    assert client.get("/api/v1/forecast?platform=ELSA&periods=1000").status_code == 422


def test_without_database_returns_503(monkeypatch):
    monkeypatch.setattr(get_settings(), "database_url", "")
    assert client.get("/api/v1/forecast?platform=ELSA").status_code == 503


@pytest.fixture()
def has_forecast():
    url = get_settings().database_url
    if not url:
        pytest.skip("Chưa cấu hình DATABASE_URL")
    try:
        with psycopg.connect(url, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM dw.fact_forecast")
            if cur.fetchone()[0] == 0:
                pytest.skip("dw.fact_forecast còn trống (chạy python src/ml/forecast/m3_forecast.py write)")
    except psycopg.Error:
        pytest.skip("Không kết nối được CSDL cục bộ")


def test_unknown_platform_returns_404(has_forecast):
    assert client.get("/api/v1/forecast?platform=KHONG_CO_NEN_TANG").status_code == 404


def test_known_platform_returns_requested_periods_with_both_targets(has_forecast):
    res = client.get("/api/v1/forecast?platform=elsa speak&periods=4")
    assert res.status_code == 200
    body = res.json()
    assert body["platform"] == "ELSA Speak" and len(body["periods"]) == 4 and body["message"] is None
    for period in body["periods"]:
        assert period["sentiment_index"] and period["negative_rate"]
        nr = period["negative_rate"]
        assert 0 <= nr["ci_lower"] <= nr["forecast"] <= nr["ci_upper"] <= 1
    assert body["periods"][-1]["negative_rate"]["actual"] is None  # tháng kế tiếp chưa có số thực tế


def test_short_series_platform_returns_empty_with_message(has_forecast):
    res = client.get("/api/v1/forecast?platform=DUOLINGO")
    assert res.status_code == 200 and res.json()["periods"] == [] and res.json()["message"]
