"""Kiểm thử chatbot T6 (POST /api/v1/chat, app/services/chatbot.py).

Phần phân tích câu hỏi không cần CSDL. Phần trả lời đọc kho thật ở chế độ chỉ đọc, tự bỏ qua khi chưa có DATABASE_URL.
"""

from __future__ import annotations

from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import require_user
from app.main import app
from app.schemas.auth import UserOut
from app.services import chatbot as cb

NAMES = ["Busuu", "DUOLINGO", "ELSA Speak", "HOCMAI", "Khan Academy", "MONKEY", "Memrise", "Quizlet", "VUIHOC"]
DONE, LAST = date(2026, 10, 1), date(2026, 11, 1)
client = TestClient(app)


def parse(text: str) -> cb.Query:
    return cb.parse_question(text, NAMES, DONE, LAST)


# ------------------------------------------------------------------------------------------- phân tích câu hỏi
@pytest.mark.parametrize("text,intent", [
    ("Tình hình ELSA Speak tháng trước thế nào?", "overview"),
    ("Tình hình các nền tảng ra sao", "overview"),          # "nền tảng" không được hiểu là "tăng"
    ("Nền tảng nào có Sentiment Index cao nhất?", "compare"),
    ("Xu hướng của DUOLINGO 6 tháng gần đây", "trend"),
    ("Dự báo tháng tới của ELSA Speak", "forecast"),
    ("So sánh nền tảng trong nước và quốc tế", "compare_group"),
    ("So sánh ELSA và Busuu", "compare_platforms"),
    ("Có cảnh báo nào cần xử lý không?", "alert"),
    ("Báo chí nói gì về Duolingo?", "news"),
    ("Có bao nhiêu đánh giá?", "overview"),                 # "bao nhiêu" không phải báo chí
    ("Sentiment Index được tính như thế nào?", "explain"),
    ("Sự kiện khuyến mãi của HOCMAI", "event"),
    ("hôm nay trời đẹp", "unknown"),
])
def test_detect_intent(text, intent):
    assert parse(text).intent == intent


def test_platform_aliases_and_order():
    assert parse("so sánh vui hoc với hoc mai và elsa").platforms == ["VUIHOC", "HOCMAI", "ELSA Speak"]
    assert parse("khan academy thế nào").platforms == ["Khan Academy"]
    assert parse("tình hình chung").platforms == []


@pytest.mark.parametrize("text,start,end", [
    ("ELSA tháng 10/2026", date(2026, 10, 1), date(2026, 10, 1)),
    ("ELSA 7/2025", date(2025, 7, 1), date(2025, 7, 1)),
    ("ELSA quý 3/2026", date(2026, 7, 1), date(2026, 9, 1)),
    ("ELSA năm 2025", date(2025, 1, 1), date(2025, 12, 1)),
    ("ELSA tháng trước", DONE, DONE),
    ("ELSA tháng này", LAST, LAST),
    ("ELSA tháng 12", date(2025, 12, 1), date(2025, 12, 1)),  # tháng 12 chưa tới thì lấy năm trước
])
def test_parse_period(text, start, end):
    period = parse(text).period
    assert (period.start, period.end) == (start, end)


def test_recent_months_and_ranking_direction():
    assert parse("xu hướng ELSA 12 tháng gần đây").months == 12
    assert parse("nền tảng nào có SI cao nhất").descending is True
    assert parse("nền tảng nào có SI thấp nhất").descending is False
    q = parse("nền tảng nào có tỷ lệ tiêu cực tệ nhất")
    assert q.metric == "negative_rate" and q.descending is True   # tệ nhất = tiêu cực CAO nhất
    assert parse("app nào tốt nhất về tỷ lệ tiêu cực").descending is False


def test_number_format():
    assert cb.num(1234.56) == "1.234,6" and cb.num(29061, 0) == "29.061" and cb.pct(0.2872) == "28,7%"


# ------------------------------------------------------------------------------------------- API
def test_chat_requires_login():
    assert client.post("/api/v1/chat", json={"question": "xin chào"}).status_code == 401


@pytest.fixture()
def logged_in():
    app.dependency_overrides[require_user] = lambda: UserOut(username="kiem_thu", role="viewer")
    yield
    app.dependency_overrides.pop(require_user, None)


def test_blank_question_422_and_no_database_503(logged_in, monkeypatch):
    assert client.post("/api/v1/chat", json={"question": "   "}).status_code == 422
    assert client.post("/api/v1/chat", json={"question": ""}).status_code == 422
    monkeypatch.setattr(get_settings(), "database_url", "")
    assert client.post("/api/v1/chat", json={"question": "ELSA thế nào"}).status_code == 503


@pytest.fixture()
def db(logged_in):
    url = get_settings().database_url
    if not url:
        pytest.skip("Chưa cấu hình DATABASE_URL")
    try:
        with psycopg.connect(url, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM dw.v_platform_month")
            if cur.fetchone()[0] == 0:
                pytest.skip("dw.fact_platform_period còn trống")
    except psycopg.Error:
        pytest.skip("Không kết nối được CSDL cục bộ")
    return url


def ask(question: str) -> dict:
    response = client.post("/api/v1/chat", json={"question": question})
    assert response.status_code == 200, response.text
    return response.json()


def test_overview_numbers_match_warehouse(db):
    body = ask("Tình hình ELSA Speak tháng 10/2026")
    assert body["intent"] == "overview" and body["platforms"] == ["ELSA Speak"]
    with psycopg.connect(db) as conn, conn.cursor() as cur:
        cur.execute("SELECT new_review_count FROM dw.v_platform_month WHERE platform_name = 'ELSA Speak' "
                    "AND month_start = '2026-10-01'")
        row = cur.fetchone()
    if row:
        assert body["data"][0]["new_review_count"] == row[0]
        assert f"{row[0]} đánh giá" in body["answer"].replace(".", "")


def test_ranking_excludes_small_samples(db):
    body = ask("Nền tảng nào có Sentiment Index cao nhất năm 2025?")
    assert body["intent"] == "compare"
    assert all(r["new_review_count"] >= cb.MIN_SAMPLE for r in body["data"])
    values = [r["sentiment_index"] for r in body["data"]]
    assert values == sorted(values, reverse=True)


@pytest.mark.parametrize("question,intent", [
    ("Xu hướng của DUOLINGO 6 tháng gần đây", "trend"),
    ("Dự báo tháng tới của ELSA Speak", "forecast"),
    ("So sánh nền tảng trong nước và quốc tế", "compare_group"),
    ("Có cảnh báo nào cần xử lý không?", "alert"),
    ("Báo chí nói gì về các nền tảng?", "news"),
    ("Sự kiện khuyến mãi của HOCMAI", "event"),
    ("BHI là gì", "explain"),
    ("Có bao nhiêu đánh giá?", "overview"),
    ("hôm nay trời đẹp", "unknown"),
])
def test_every_intent_answers(db, question, intent):
    body = ask(question)
    assert body["intent"] == intent and body["answer"] and body["mode"] == "truy_van_tham_so"
    assert body["suggestions"]


def test_injection_attempt_is_just_text(db):
    body = ask("ELSA'; DROP TABLE dw.fact_review; --")
    assert body["intent"] == "overview"
    with psycopg.connect(db) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dw.fact_review")
        assert cur.fetchone()[0] > 0


def test_trend_handles_none_sentiment_index():
    """Kiểm tra Responder._trend xử lý an toàn khi tháng đầu hoặc tháng cuối có sentiment_index = None."""
    class MockStore:
        latest_complete = date(2026, 10, 1)
        latest_data = date(2026, 11, 1)

        def month_bounds(self, today):
            return self.latest_complete, self.latest_data

        def platform_names(self):
            return ["ELSA Speak"]

        def monthly(self, name, months, until):
            # Tháng đầu có None, tháng giữa có số, tháng cuối có None
            return [
                {"month_start": date(2026, 5, 1), "sentiment_index": None, "new_review_count": 10},
                {"month_start": date(2026, 6, 1), "sentiment_index": 20.5, "new_review_count": 40},
                {"month_start": date(2026, 7, 1), "sentiment_index": None, "new_review_count": 50},
            ]

    responder = cb.Responder(MockStore())
    result = responder.answer("Xu hướng của ELSA Speak 6 tháng gần đây")
    assert result.intent == "trend"
    assert "biến động chưa xác định" in result.answer
    assert "Cao nhất 06/2026 (20,5)" in result.answer

    class MockStoreAllNone:
        latest_complete = date(2026, 10, 1)
        latest_data = date(2026, 11, 1)

        def month_bounds(self, today):
            return self.latest_complete, self.latest_data

        def platform_names(self):
            return ["ELSA Speak"]

        def monthly(self, name, months, until):
            return [
                {"month_start": date(2026, 5, 1), "sentiment_index": None, "new_review_count": 10},
                {"month_start": date(2026, 6, 1), "sentiment_index": None, "new_review_count": 20},
            ]

    res_all_none = cb.Responder(MockStoreAllNone()).answer("Xu hướng của ELSA Speak 6 tháng gần đây")
    assert res_all_none.intent == "trend"
    assert "biến động chưa xác định" in res_all_none.answer

