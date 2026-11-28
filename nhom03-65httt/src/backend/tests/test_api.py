from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_db_unavailable_without_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    try:
        response = client.get("/health/db")
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


def test_health_db_error_does_not_leak_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:bi-mat-123@127.0.0.1:1/khong_ton_tai")
    get_settings.cache_clear()
    try:
        response = client.get("/health/db")
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503
    assert "bi-mat-123" not in response.text


def test_platforms_from_config():
    response = client.get("/api/v1/platforms")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 9
    ids = {item["id"] for item in data}
    assert {"ELSA Speak", "DUOLINGO", "Quizlet"} <= ids
    assert {item["group"] for item in data} == {"trong_nuoc", "quoc_te"}


def test_chat_requires_authentication():
    assert client.post("/api/v1/chat", json={"question": "xin chào"}).status_code == 401  # chatbot cần đăng nhập


def test_validation_rejects_empty_text():
    assert client.post("/api/v1/predict/sentiment", json={"text": ""}).status_code == 422
