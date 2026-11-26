from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_aspects_api_returns_opposing_sentiments_for_two_aspects():
    response = client.post(
        "/api/v1/predict/aspects",
        json={"text": "Giảng viên dạy hay nhưng ứng dụng lag"},
    )

    assert response.status_code == 200
    aspects = {item["aspect_name"]: item for item in response.json()["aspects"]}
    assert aspects["Academic"]["sentiment_label"] == "tich_cuc"
    assert aspects["Technical"]["sentiment_label"] == "tieu_cuc"


def test_aspects_api_returns_empty_list_when_no_aspect_is_mentioned():
    response = client.post("/api/v1/predict/aspects", json={"text": "Chào mọi người"})

    assert response.status_code == 200
    assert response.json() == {"aspects": []}


def test_aspects_api_rejects_blank_input():
    assert client.post("/api/v1/predict/aspects", json={"text": "   "}).status_code == 422
