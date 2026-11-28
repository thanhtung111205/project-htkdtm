"""Kiểm thử API cảnh báo HU3: auth, 503/422/404 và dữ liệu test tự dọn."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import require_admin, require_user
from app.main import app
from app.schemas.auth import UserOut

client = TestClient(app)


@pytest.fixture()
def viewer_logged_in():
    app.dependency_overrides[require_user] = lambda: UserOut(username="kiem_thu_viewer", role="viewer")
    yield
    app.dependency_overrides.pop(require_user, None)


@pytest.fixture()
def admin_logged_in():
    app.dependency_overrides[require_admin] = lambda: UserOut(username="kiem_thu_admin", role="admin")
    yield
    app.dependency_overrides.pop(require_admin, None)


def test_alerts_require_login():
    assert client.get("/api/v1/alerts").status_code == 401


def test_viewer_patch_returns_403():
    def viewer_admin_denied():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Yêu cầu quyền Quản trị viên (Admin)",
        )

    app.dependency_overrides[require_admin] = viewer_admin_denied
    try:
        response = client.patch("/api/v1/alerts/1/status", json={"status": "da_xu_ly"})
    finally:
        app.dependency_overrides.pop(require_admin, None)
    assert response.status_code == 403


def test_status_invalid_returns_422(viewer_logged_in, admin_logged_in):
    response = client.patch("/api/v1/alerts/1/status", json={"status": "khong_hop_le"})
    assert response.status_code == 422


def test_missing_database_returns_503(viewer_logged_in, monkeypatch):
    monkeypatch.setattr(get_settings(), "database_url", "")
    assert client.get("/api/v1/alerts").status_code == 503


def test_invalid_date_range_returns_422(viewer_logged_in):
    response = client.get("/api/v1/alerts?start_date=2026-11-30&end_date=2026-11-01")
    assert response.status_code == 422


@pytest.fixture()
def alerts_db(viewer_logged_in, admin_logged_in):
    url = get_settings().database_url
    if not url:
        pytest.skip("Chưa cấu hình DATABASE_URL")
    try:
        conn = psycopg.connect(url, connect_timeout=3)
        conn.autocommit = False
    except psycopg.Error as exc:
        pytest.skip(f"Không kết nối được CSDL cục bộ: {type(exc).__name__}")

    inserted: list[int] = []
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dw.fact_alert WHERE metric_name = 'test_hu3'")

            cur.execute("SELECT platform_key, platform_name FROM dw.dim_platform WHERE platform_name IN ('ELSA Speak','DUOLINGO') ORDER BY platform_name")
            platforms = {name: key for key, name in cur.fetchall()}
            if "ELSA Speak" not in platforms or "DUOLINGO" not in platforms:
                pytest.skip("Thiếu nền tảng ELSA Speak hoặc DUOLINGO trong dw.dim_platform")

            cur.execute("SELECT aspect_key, aspect_name FROM dw.dim_aspect LIMIT 1")
            aspect_row = cur.fetchone()
            if aspect_row:
                aspect_key = int(aspect_row[0])
            else:
                aspect_key = None

            cur.execute("SELECT time_key FROM dw.dim_time ORDER BY full_date DESC LIMIT 1")
            time_row = cur.fetchone()
            if time_row:
                time_key = int(time_row[0])
            else:
                pytest.skip("dw.dim_time không có dữ liệu")

            now = datetime.now(timezone.utc)
            values = [
                (time_key, platforms["ELSA Speak"], aspect_key, 30.0, 20.0, now - timedelta(hours=1), "moi", now - timedelta(minutes=30), "Product Manager", "Kiểm tra tỷ lệ tiêu cực"),
                (time_key, platforms["DUOLINGO"], None, 24.0, 20.0, now - timedelta(hours=2), "dang_xu_ly", now - timedelta(minutes=20), "Customer Success", "Theo dõi nền tảng"),
                (time_key, platforms["ELSA Speak"], None, 40.0, 20.0, now - timedelta(hours=3), "da_xu_ly", now - timedelta(minutes=10), "Đội kỹ thuật", "Đã xử lý"),
            ]

            for time_key_value, platform_key, aspect_key_value, metric_value, threshold, detected_at, status_value, notified_at, department, action in values:
                cur.execute("""
                    INSERT INTO dw.fact_alert
                        (time_key, platform_key, aspect_key, metric_name, metric_value, threshold,
                         detected_at, status, recommended_action, responsible_department, notified_at)
                    VALUES (%s,%s,%s,'test_hu3',%s,%s,%s,%s,%s,%s,%s)
                    RETURNING alert_key
                """, (time_key_value, platform_key, aspect_key_value, metric_value, threshold,
                      detected_at, status_value, action, department, notified_at))
                inserted.append(int(cur.fetchone()[0]))
        conn.commit()
        yield url, inserted
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM dw.fact_alert WHERE metric_name = 'test_hu3'")
            conn.commit()
        finally:
            conn.close()


def test_default_excludes_resolved_and_platform_filter(alerts_db):
    _url, _ids = alerts_db
    response = client.get("/api/v1/alerts")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(item["status"] != "da_xu_ly" for item in body["items"])

    elsa = client.get("/api/v1/alerts?platform=elsa%20speak")
    assert elsa.status_code == 200
    assert elsa.json()["total"] == 1
    assert elsa.json()["items"][0]["platform_name"] == "ELSA Speak"


def test_severity_rules_and_summary(alerts_db):
    _url, _ids = alerts_db
    response = client.get("/api/v1/alerts")
    items = {item["platform_name"]: item for item in response.json()["items"]}
    assert items["ELSA Speak"]["severity"] == "cao"  # 30 / 20 = 1.5
    assert items["DUOLINGO"]["severity"] == "trung_binh"  # 24 / 20 = 1.2

    summary = client.get("/api/v1/alerts/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["total"] == 2
    assert body["by_platform"] == {"DUOLINGO": 1, "ELSA Speak": 1}
    assert body["by_severity"] == {"cao": 1, "trung_binh": 1, "thap": 0}


def test_patch_detail_repeat_and_notified_not_changed(alerts_db):
    url, ids = alerts_db
    alert_key = ids[0]

    with psycopg.connect(url, connect_timeout=3) as conn, conn.cursor() as cur:
        cur.execute("SELECT notified_at FROM dw.fact_alert WHERE alert_key = %s", (alert_key,))
        notified_before = cur.fetchone()[0]

    patched = client.patch(f"/api/v1/alerts/{alert_key}/status", json={"status": "da_xu_ly"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "da_xu_ly"

    repeated = client.patch(f"/api/v1/alerts/{alert_key}/status", json={"status": "da_xu_ly"})
    assert repeated.status_code == 200

    default_list = client.get("/api/v1/alerts")
    assert alert_key not in {item["alert_key"] for item in default_list.json()["items"]}

    with psycopg.connect(url, connect_timeout=3) as conn, conn.cursor() as cur:
        cur.execute("SELECT notified_at FROM dw.fact_alert WHERE alert_key = %s", (alert_key,))
        notified_after = cur.fetchone()[0]
    assert notified_after == notified_before


def test_unknown_alert_and_detail(alerts_db):
    _url, ids = alerts_db
    missing = client.get("/api/v1/alerts/9223372036854770000")
    assert missing.status_code == 404

    detail = client.get(f"/api/v1/alerts/{ids[0]}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["alert_key"] == ids[0]
    assert body["aspect_name"] is not None or body["platform_name"]
