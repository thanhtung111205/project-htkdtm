"""Kiểm thử ghi cảnh báo bất thường vào dw.fact_alert: chạy lại không trùng. Giao dịch hoàn tác cuối bài."""

import sys
from pathlib import Path

import pytest

ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL_DIR))

from common import connect  # noqa: E402
from detect_anomaly import write_alerts  # noqa: E402

from app.services.anomaly import load_config  # noqa: E402  (đã thêm src/backend vào sys.path bởi detect_anomaly)


@pytest.fixture()
def conn():
    try:
        connection = connect(connect_timeout=3)
    except Exception as exc:
        pytest.skip(f"Không kết nối được PostgreSQL cục bộ: {type(exc).__name__}")
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM dw.fact_review")
            if cur.fetchone()[0] == 0:
                pytest.skip("CSDL chưa có dữ liệu đánh giá")
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_rerun_does_not_duplicate_alerts(conn):
    cfg = load_config()
    first = write_alerts(conn, cfg, all_periods=True)
    second = write_alerts(conn, cfg, all_periods=True)
    assert first["inserted"] == first["anomalies"] > 0
    assert second["inserted"] == 0 and second["anomalies"] == first["anomalies"]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM (SELECT 1 FROM dw.fact_alert WHERE metric_name = %s "
            "GROUP BY platform_key, time_key HAVING count(*) > 1) d", (cfg["metric_name"],))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM dw.fact_alert WHERE status <> 'moi' AND metric_name = %s", (cfg["metric_name"],))
        assert cur.fetchone()[0] == 0


def test_short_series_reported_without_error(conn):
    summary = write_alerts(conn, load_config(), platform="DUOLINGO")
    assert summary["inserted"] == 0 and summary["skipped_short"]
