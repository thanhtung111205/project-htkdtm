"""Kiểm thử phát hiện bất thường (N4): chuỗi mẫu có đột biến cố tình chèn, và mã HTTP của API."""

from __future__ import annotations

from datetime import date, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.anomaly import ANCHOR, detect, period_start

client = TestClient(app)


def _series(rates, total=100):
    """Chuỗi kỳ hai tuần liên tiếp từ ANCHOR với tỷ lệ tiêu cực cho trước."""
    return [(ANCHOR + timedelta(days=14 * i), total, round(r * total)) for i, r in enumerate(rates)]


def test_period_start_is_biweekly_monday():
    assert period_start(ANCHOR) == ANCHOR
    assert period_start(ANCHOR + timedelta(days=13)) == ANCHOR
    assert period_start(ANCHOR + timedelta(days=14)) == ANCHOR + timedelta(days=14)
    assert period_start(date(2026, 11, 26)).weekday() == 0


def test_spike_detected_in_correct_period():
    base = [0.20, 0.22, 0.19, 0.21, 0.20, 0.23, 0.18, 0.21]
    series = _series(base + [0.21, 0.55, 0.22])  # đột biến ở chỉ số 9
    flagged = [r.period_start for r in detect(series) if r.is_anomaly]
    assert flagged == [series[9][0]]


def test_flat_series_and_small_wobble_not_flagged():
    assert not any(r.is_anomaly for r in detect(_series([0.2] * 12)))
    wobble = [0.20] * 8 + [0.22, 0.20, 0.23]  # tăng dưới 5 điểm phần trăm
    assert not any(r.is_anomaly for r in detect(_series(wobble)))


def test_fewer_than_eight_prior_periods_never_flags():
    results = detect(_series([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.9]))
    assert len(results) == 8 and not any(r.is_anomaly for r in results)


def test_sparse_periods_are_dropped():
    series = _series([0.2] * 9, total=5)  # dưới min_reviews
    assert detect(series) == []


def test_api_validation_returns_422():
    assert client.get("/api/v1/anomaly").status_code == 422
    assert client.get("/api/v1/anomaly?platform=ELSA&periods=0").status_code == 422
    assert client.get("/api/v1/anomaly?platform=ELSA&periods=abc").status_code == 422


def test_api_without_database_returns_503(monkeypatch):
    monkeypatch.setattr(get_settings(), "database_url", "")
    assert client.get("/api/v1/anomaly?platform=ELSA").status_code == 503


@pytest.fixture()
def db_ready():
    url = get_settings().database_url
    if not url:
        pytest.skip("Chưa cấu hình DATABASE_URL")
    try:
        with psycopg.connect(url, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM dw.fact_review")
            if cur.fetchone()[0] == 0:
                pytest.skip("CSDL chưa có dữ liệu đánh giá")
    except psycopg.Error:
        pytest.skip("Không kết nối được CSDL cục bộ")


def test_api_unknown_platform_404_and_known_200(db_ready):
    assert client.get("/api/v1/anomaly?platform=KHONG_CO_NEN_TANG").status_code == 404
    res = client.get("/api/v1/anomaly?platform=elsa speak&periods=5")
    assert res.status_code == 200
    body = res.json()
    assert body["platform"] == "ELSA Speak" and len(body["periods"]) == 5 and body["status"] == "ok"


def test_api_short_series_is_message_not_error(db_ready):
    res = client.get("/api/v1/anomaly?platform=DUOLINGO")
    assert res.status_code == 200
    assert res.json()["status"] == "khong_du_ky" and res.json()["message"]
