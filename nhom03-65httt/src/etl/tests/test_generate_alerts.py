"""Kiểm thử T7 (generate_alerts.py): chọn bộ phận và hành động, câu dẫn chứng, điền vào dw.fact_alert.

Phần hàm thuần không cần CSDL. Phần CSDL chạy trong giao dịch và hoàn tác cuối bài, không ghi vào kho thật.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL_DIR))

import generate_alerts as g  # noqa: E402
from common import connect  # noqa: E402

DEPARTMENTS = {"Product Manager", "Customer Success", "Đội kỹ thuật", "Marketing và Kinh doanh", "Ban điều hành"}
RULES = g.load_rules()


def _alert(**over):
    alert = {"metric_name": "negative_rate_2w", "metric_value": 0.45, "threshold": 0.38, "platform_name": "ELSA Speak",
             "day": date(2026, 11, 2), "aspect_name": None}
    alert.update(over)
    return alert


def test_every_rule_uses_an_allowed_department_and_formats():
    entries = list(RULES["aspects"].values()) + list(RULES["metrics"].values()) + [RULES["default"]]
    for entry in entries:
        assert entry["department"] in DEPARTMENTS
        entry["action"].format(platform="X", period="Y", metric="Z")  # không thiếu hay thừa chỗ thay


def test_negative_rate_alert_without_aspect_data():
    action, dept = g.build_recommendation(RULES, _alert(), {"reviews": 40, "negative": 18, "dominant": None})
    assert dept == "Customer Success"
    assert "ELSA Speak" in action and "02/11/2026 đến 15/11/2026" in action
    assert "Dẫn chứng: tỷ lệ tiêu cực 45% (18/40 đánh giá có sao), ngưỡng 38%." in action
    assert "Ban điều hành" not in action


def test_large_exceedance_escalates():
    action, _ = g.build_recommendation(RULES, _alert(metric_value=0.62), {"reviews": 50, "negative": 31, "dominant": None})
    assert action.endswith("báo cáo Ban điều hành.")


def test_dominant_aspect_routes_to_its_department():
    evidence = {"reviews": 40, "negative": 18, "dominant": ("Technical", 0.6, 10)}
    action, dept = g.build_recommendation(RULES, _alert(), evidence)
    assert dept == "Đội kỹ thuật" and "Technical (60% của 10 lượt nhắc tiêu cực)" in action


@pytest.mark.parametrize("dominant", [("Technical", 0.3, 10), ("Technical", 0.9, 3)])
def test_weak_dominant_aspect_falls_back_to_metric(dominant):
    _, dept = g.build_recommendation(RULES, _alert(), {"reviews": 40, "negative": 18, "dominant": dominant})
    assert dept == "Customer Success"


def test_alert_aspect_wins_and_unknown_metric_uses_default():
    _, dept = g.build_recommendation(RULES, _alert(aspect_name="Pricing"), {"reviews": 0, "negative": 0})
    assert dept == "Marketing và Kinh doanh"
    action, dept = g.build_recommendation(RULES, _alert(metric_name="share_of_voice", metric_value=0.1, threshold=0.2,
                                                        day=date(2026, 11, 1)), {})
    assert dept == "Product Manager" and "share_of_voice" in action and "kỳ 01/11/2026" in action


def test_pct_format():
    assert g._pct(0.45) == "45%" and g._pct(0.7083) == "70,8%" and g._pct(0.0) == "0%"


@pytest.fixture()
def conn():
    try:
        connection = connect(connect_timeout=3)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Không kết nối được PostgreSQL cục bộ: {type(exc).__name__}")
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT to_regclass('dw.fact_alert') IS NOT NULL AND EXISTS ("
                        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'dw' "
                        "AND table_name = 'fact_alert' AND column_name = 'recommended_action')")
            if not cur.fetchone()[0]:
                pytest.skip("CSDL chưa có migration 0006")
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _insert_alert(cur, action=None) -> int:
    cur.execute(
        """
        INSERT INTO dw.fact_alert (time_key, platform_key, metric_name, metric_value, threshold, detected_at, recommended_action)
        SELECT 20261102, platform_key, 'negative_rate_2w', 0.5, 0.3, now(), %s
        FROM dw.dim_platform WHERE platform_name = 'ELSA Speak'
        RETURNING alert_key
        """,
        (action,),
    )
    return cur.fetchone()[0]


def test_fill_recommendations_fills_empty_and_keeps_existing(conn):
    with conn.cursor() as cur:
        empty, kept = _insert_alert(cur), _insert_alert(cur, "Hành động do người nhập")
    g.fill_recommendations(conn, RULES)
    with conn.cursor() as cur:
        cur.execute("SELECT alert_key, recommended_action, responsible_department FROM dw.fact_alert "
                    "WHERE alert_key = ANY(%s) ORDER BY alert_key", ([empty, kept],))
        rows = {r[0]: r[1:] for r in cur.fetchall()}
    assert "Dẫn chứng:" in rows[empty][0] and rows[empty][1] == "Customer Success"
    assert rows[kept][0] == "Hành động do người nhập" and rows[kept][1] == "Customer Success"
    assert g.fill_recommendations(conn, RULES) == 0  # chạy lại không còn gì để điền


def test_run_twice_creates_no_duplicates(conn):
    first = g.run(conn)
    second = g.run(conn)
    assert second["inserted"] == 0 and second["filled"] == 0
    assert first["filled"] >= first["inserted"]
