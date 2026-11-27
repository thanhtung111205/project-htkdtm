"""Kiểm thử bổ sung migration 0006 (G1 đến G4): cột mới, hàm đồng bộ, nạp giờ và độ dài, thuộc tính nền tảng.

Các ca CSDL tự bỏ qua khi chưa kết nối được PostgreSQL hoặc chưa áp dụng migration 0006; mọi thay đổi được hoàn tác.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL_DIR))
sys.path.insert(0, str(ETL_DIR / "load"))

from common import connect  # noqa: E402
from load_platform_attributes import CATEGORIES, read_developers, update_platform_attributes  # noqa: E402


@pytest.fixture()
def conn():
    try:
        connection = connect(connect_timeout=3)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Không kết nối được PostgreSQL cục bộ: {type(exc).__name__}")
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass('dw.dim_hour') IS NOT NULL")
        if not cur.fetchone()[0]:
            connection.close()
            pytest.skip("Chưa chạy migration 0006")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


# ---------------------------------------------------------------- G2: đọc nhà phát triển (không cần CSDL)
def _write_app_info(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["snapshot_date", "product", "store", "developer"])
        writer.writeheader()
        writer.writerows(rows)


def test_read_developers_prefers_app_store_and_falls_back_to_google_play(tmp_path):
    path = tmp_path / "app_info.csv"
    _write_app_info(path, [
        {"snapshot_date": "2026-11-18", "product": "ELSA Speak", "store": "google_play", "developer": "ELSA Speak"},
        {"snapshot_date": "2026-11-18", "product": "ELSA Speak", "store": "app_store_vn", "developer": "ELSA, Corp."},
        {"snapshot_date": "2026-11-18", "product": "Quizlet", "store": "google_play", "developer": "Quizlet Inc"},
        {"snapshot_date": "2026-11-18", "product": "Quizlet", "store": "app_store_vn", "developer": ""},
    ])
    assert read_developers(path) == {"ELSA Speak": "ELSA, Corp.", "Quizlet": "Quizlet Inc"}


def test_read_developers_rejects_missing_columns_and_missing_file(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("product,store\nA,google_play\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Thiếu cột"):
        read_developers(bad)
    with pytest.raises(FileNotFoundError):
        read_developers(tmp_path / "khong_co.csv")


def test_categories_cover_the_nine_platforms_with_allowed_values():
    assert len(CATEGORIES) == 9
    assert set(CATEGORIES.values()) <= {"hoc_tong_hop", "ngoai_ngu"}


# ---------------------------------------------------------------- G1: thời gian
def test_dim_time_weekday_and_weekend_are_generated_correctly(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT day_of_week, is_weekend FROM dw.dim_time WHERE full_date = DATE '2026-11-21'")   # thứ Bảy
        assert cur.fetchone() == (6, True)
        cur.execute("SELECT day_of_week, is_weekend FROM dw.dim_time WHERE full_date = DATE '2026-11-23'")   # thứ Hai
        assert cur.fetchone() == (1, False)
        cur.execute("SELECT count(*) FROM dw.dim_time WHERE is_weekend <> (day_of_week >= 6) OR day_of_week NOT BETWEEN 1 AND 7")
        assert cur.fetchone()[0] == 0


def test_new_dim_time_rows_get_weekday_columns_without_changing_insert_code(conn):
    """Mã nạp ngày cũ không liệt kê hai cột mới; chúng phải tự có giá trị."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dw.dim_time (time_key, full_date, week, month, quarter, year) "
            "VALUES (20991231, DATE '2099-12-31', 53, 12, 4, 2099)"
        )
        cur.execute("SELECT day_of_week, is_weekend FROM dw.dim_time WHERE time_key = 20991231")
        assert cur.fetchone() == (4, False)    # 31/12/2099 là thứ Năm


def test_dim_hour_has_24_hours_with_consistent_day_parts(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT hour_key, day_part FROM dw.dim_hour ORDER BY hour_key")
        rows = cur.fetchall()
    assert [r[0] for r in rows] == list(range(24))
    assert {h: p for h, p in rows}[5] == "dem" and {h: p for h, p in rows}[6] == "sang"
    assert {h: p for h, p in rows}[12] == "chieu" and {h: p for h, p in rows}[18] == "toi"


# ---------------------------------------------------------------- G3: đồng bộ nhãn và cờ lệch pha
def test_refresh_function_sets_label_score_and_mismatch_flag_only_for_requested_keys(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT model_key FROM dw.dim_model WHERE model_name = 'M1_phobert'")
        model_key = cur.fetchone()[0]
        cur.execute("SELECT review_key, rating FROM dw.fact_review WHERE rating IS NOT NULL ORDER BY review_key LIMIT 4")
        rows = cur.fetchall()
        if len(rows) < 4:
            pytest.skip("Kho chưa đủ đánh giá có số sao")
        keys = [r[0] for r in rows]
        cur.execute("DELETE FROM dw.fact_review_sentiment WHERE review_key = ANY(%s)", (keys,))
        cur.execute("UPDATE dw.fact_review SET sentiment_label = NULL, sentiment_score = NULL, is_mismatch = NULL WHERE review_key = ANY(%s)", (keys,))
        # ép số sao để kiểm tra bốn tình huống: 5 sao tiêu cực (lệch), 1 sao tích cực (lệch), 5 sao tích cực, 3 sao tiêu cực
        for key, rating, label in ((keys[0], 5, "tieu_cuc"), (keys[1], 1, "tich_cuc"), (keys[2], 5, "tich_cuc"), (keys[3], 3, "tieu_cuc")):
            cur.execute("UPDATE dw.fact_review SET rating = %s WHERE review_key = %s", (rating, key))
            cur.execute("INSERT INTO dw.fact_review_sentiment (review_key, model_key, sentiment_label, sentiment_score, confidence) "
                        "VALUES (%s, %s, %s, 0.5, 0.9)", (key, model_key, label))
        cur.execute("SELECT dw.refresh_fact_review_sentiment(%s)", ([keys[0], keys[1], keys[2]],))      # cố ý bỏ khóa thứ tư
        assert cur.fetchone()[0] == 3
        cur.execute("SELECT review_key, sentiment_label, is_mismatch FROM dw.fact_review WHERE review_key = ANY(%s) ORDER BY review_key", (keys,))
        got = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        assert got[keys[0]] == ("tieu_cuc", True) and got[keys[1]] == ("tich_cuc", True) and got[keys[2]] == ("tich_cuc", False)
        assert got[keys[3]] == (None, None)                                                              # chưa đồng bộ
        cur.execute("SELECT dw.refresh_fact_review_sentiment(%s)", ([keys[0], keys[1], keys[2]],))
        assert cur.fetchone()[0] == 0                                                                    # chạy lại không đổi gì
        cur.execute("SELECT dw.refresh_fact_review_sentiment(%s)", (keys,))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT is_mismatch FROM dw.fact_review WHERE review_key = %s", (keys[3],))
        assert cur.fetchone()[0] is False                                                                # 3 sao không bao giờ lệch pha


def test_mismatch_is_null_when_rating_is_missing(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT model_key FROM dw.dim_model WHERE model_name = 'M1_phobert'")
        model_key = cur.fetchone()[0]
        cur.execute("SELECT review_key FROM dw.fact_review ORDER BY review_key LIMIT 1")
        key = cur.fetchone()[0]
        cur.execute("UPDATE dw.fact_review SET rating = NULL, sentiment_label = NULL, is_mismatch = NULL WHERE review_key = %s", (key,))
        cur.execute("DELETE FROM dw.fact_review_sentiment WHERE review_key = %s", (key,))
        cur.execute("INSERT INTO dw.fact_review_sentiment (review_key, model_key, sentiment_label, sentiment_score, confidence) VALUES (%s, %s, 'tieu_cuc', -0.9, 0.9)", (key, model_key))
        cur.execute("SELECT dw.refresh_fact_review_sentiment(%s)", ([key],))
        cur.execute("SELECT sentiment_label, is_mismatch FROM dw.fact_review WHERE review_key = %s", (key,))
        assert cur.fetchone() == ("tieu_cuc", None)


def test_review_length_and_hour_key_are_filled_for_loaded_reviews(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dw.fact_review WHERE review_length IS NULL OR review_length < 0")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM dw.fact_review f JOIN clean.review_text c USING (review_key) WHERE f.review_length <> length(c.text)")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT min(hour_key), max(hour_key) FROM dw.fact_review")
        low, high = cur.fetchone()
        assert (low, high) == (None, None) or (0 <= low <= high <= 23)


# ---------------------------------------------------------------- G4: cảnh báo
def test_alert_view_exposes_action_and_department_columns(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT platform_key FROM dw.dim_platform ORDER BY platform_key LIMIT 1")
        platform_key = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO dw.fact_alert (time_key, platform_key, metric_name, metric_value, threshold, detected_at, status, "
            "recommended_action, responsible_department) "
            "VALUES (20261126, %s, 'thu_nghiem_0006', 1, 2, now(), 'moi', 'Hotfix trong 48 giờ', 'Đội kỹ thuật')", (platform_key,))
        cur.execute("SELECT recommended_action, responsible_department FROM dw.v_alert_open WHERE metric_name = 'thu_nghiem_0006'")
        assert cur.fetchone() == ("Hotfix trong 48 giờ", "Đội kỹ thuật")


# ---------------------------------------------------------------- G2: cập nhật thuộc tính nền tảng
def test_update_platform_attributes_sets_values_and_is_idempotent(conn):
    developers = {"ELSA Speak": "ELSA, Corp.", "DUOLINGO": "Duolingo, Inc."}
    first = update_platform_attributes(conn, developers)
    second = update_platform_attributes(conn, developers)
    assert first == second and first["platforms"] >= 9
    with conn.cursor() as cur:
        cur.execute("SELECT developer, category FROM dw.dim_platform WHERE platform_name = 'ELSA Speak'")
        assert cur.fetchone() == ("ELSA, Corp.", "ngoai_ngu")
        cur.execute("SELECT category FROM dw.dim_platform WHERE platform_name = 'Quizlet'")
        assert cur.fetchone()[0] == "hoc_tong_hop"
    assert "VUIHOC" in first["without_developer"]          # nguồn thiếu thì báo, không tự đặt


def test_category_constraint_rejects_unknown_values(conn):
    import psycopg
    with conn.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("UPDATE dw.dim_platform SET category = 'khac' WHERE platform_name = 'ELSA Speak'")


# ---------------------------------------------------------------- G1, G3: đánh giá MỚI đi qua ETL phải có giờ và độ dài
def test_new_review_loaded_by_etl_gets_hour_key_and_review_length(conn, tmp_path):
    from load_clean import load_clean
    from load_dw import load_dw
    from load_raw import load_raw

    columns = ["source", "product", "review_id", "author_hash", "rating", "text", "lang_guess", "created_at",
               "app_version", "thumbs_up", "reply_text", "crawled_at"]
    path = tmp_path / "moi.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({"source": "test_src", "product": "ELSA Speak", "review_id": "g06-1", "author_hash": "h1", "rating": "5",
                         "text": "tốt lắm", "lang_guess": "vi", "created_at": "2026-11-20T15:30:00+00:00",   # 22:30 giờ Việt Nam
                         "app_version": "1.0", "thumbs_up": "0", "reply_text": "", "crawled_at": "2026-11-21T00:00:00+00:00"})
    load_raw(conn, path)
    load_clean(conn)
    load_dw(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT f.hour_key, f.review_length, h.day_part, t.is_weekend FROM dw.fact_review f "
            "JOIN clean.review_text c USING (review_key) JOIN dw.dim_hour h USING (hour_key) JOIN dw.dim_time t USING (time_key) "
            "WHERE c.source = 'test_src' AND c.review_id = 'g06-1'")
        assert cur.fetchone() == (22, 7, "toi", False)          # 20/11/2026 là thứ Sáu
