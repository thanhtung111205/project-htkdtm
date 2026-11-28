"""Unit tests cho API KPI/BHI; mock DB nên chạy được kể cả không mở PostgreSQL."""

from datetime import date

from fastapi.testclient import TestClient

from app.api import kpi as kpi_module
from app.core.config import get_settings
from app.main import app


client = TestClient(app)


ROW = (
    date(2026, 9, 1), "ELSA Speak", "trong_nuoc", 187,
    0.72, 0.10, 4.12, 36.5, 76.38, 0.25,
)


def _enable_mock(monkeypatch, rows):
    monkeypatch.setattr(get_settings(), "database_url", "postgresql://mock")
    monkeypatch.setattr(kpi_module, "fetch_platform_month", lambda *args: rows)


def test_kpi_filters_and_response(monkeypatch):
    _enable_mock(monkeypatch, [ROW])
    response = client.get(
        "/api/v1/kpi",
        params={"platform_name": "ELSA Speak", "platform_group": "trong_nuoc",
                "start_date": "2026-09-01", "end_date": "2026-09-30"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["filters"]["platform_name"] == "ELSA Speak"
    assert body["data"][0]["new_review_count"] == 187


def test_kpi_empty_data(monkeypatch):
    _enable_mock(monkeypatch, [])
    response = client.get("/api/v1/kpi?platform_name=KHONG_CO")
    assert response.status_code == 200
    assert response.json()["status"] == "khong_co_du_lieu"
    assert response.json()["data"] == []
    assert response.json()["message"]


def test_kpi_invalid_date_range_returns_422(monkeypatch):
    monkeypatch.setattr(get_settings(), "database_url", "postgresql://mock")
    response = client.get("/api/v1/kpi?start_date=2026-10-01&end_date=2026-09-01")
    assert response.status_code == 422


def test_missing_database_returns_503(monkeypatch):
    monkeypatch.setattr(kpi_module, "resolve_database_url", lambda: "")
    assert client.get("/api/v1/kpi").status_code == 503
    assert client.get("/api/v1/bhi").status_code == 503


def test_bhi_uses_real_view_value_and_small_sample_flag(monkeypatch):
    row = (ROW[0], ROW[1], ROW[2], 20, ROW[4], ROW[5], 4.12, 36.5, 76.38, ROW[9])
    _enable_mock(monkeypatch, [row])
    response = client.get("/api/v1/bhi?platform_name=ELSA%20Speak")
    assert response.status_code == 200
    point = response.json()["data"][0]
    assert point["bhi"] == 76.38
    assert point["flags"] == ["du_lieu_it"]


def test_bhi_fallback_formula(monkeypatch):
    row = (ROW[0], ROW[1], ROW[2], 100, ROW[4], ROW[5], 4.0, 50.0, None, ROW[9])
    _enable_mock(monkeypatch, [row])
    response = client.get("/api/v1/bhi")
    assert response.status_code == 200
    point = response.json()["data"][0]
    assert point["bhi"] == 75.0
    assert point["flags"] == []


class _FakeCursor:
    def __init__(self, outcomes):
        self.outcomes = outcomes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        return None

    def fetchone(self):
        return self.outcomes.pop(0)

    def fetchall(self):
        return self.outcomes.pop(0)


class _FakeConnection:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.read_only = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self.outcomes)


def test_aspect_empty_table_is_safe(monkeypatch):
    monkeypatch.setattr(get_settings(), "database_url", "postgresql://mock")

    monkeypatch.setattr(kpi_module.psycopg, "connect", lambda *args, **kwargs: _FakeConnection([(True,), []]))
    response = client.get("/api/v1/kpi/aspects")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "khong_co_du_lieu"
    assert body["data"] == []
    assert "0 dòng" in body["message"]


def test_aspect_missing_table_is_safe(monkeypatch):
    monkeypatch.setattr(get_settings(), "database_url", "postgresql://mock")
    monkeypatch.setattr(kpi_module.psycopg, "connect", lambda *args, **kwargs: _FakeConnection([(False,) ]))
    response = client.get("/api/v1/kpi/aspects")
    assert response.status_code == 200
    assert response.json()["status"] == "khong_co_du_lieu"
    assert response.json()["data"] == []
