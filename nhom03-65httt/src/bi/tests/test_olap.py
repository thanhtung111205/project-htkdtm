"""Kiểm thử năm truy vấn OLAP (src/bi/olap/olap_queries.sql) trên PostgreSQL thật; bỏ qua nếu CSDL chưa có dữ liệu.

Kiểm tra: mỗi truy vấn ra ít nhất một dòng, tổng các mức khớp nhau, số dòng slice và dice khớp phép đếm độc lập trên fact_review.
Chỉ đọc, không ghi CSDL.
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src" / "etl"))

from common import connect  # noqa: E402

SQL_FILE = ROOT / "src" / "bi" / "olap" / "olap_queries.sql"


def load_queries() -> dict[str, str]:
    parts = re.split(r"^-- @query (\w+)\s*$", SQL_FILE.read_text(encoding="utf-8"), flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


@pytest.fixture(scope="module")
def conn():
    try:
        connection = connect(connect_timeout=3)
    except Exception as exc:
        pytest.skip(f"Không kết nối được PostgreSQL cục bộ: {type(exc).__name__}")
    connection.read_only = True
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM dw.fact_review")
        if cur.fetchone()[0] == 0:
            pytest.skip("CSDL chưa có dữ liệu đánh giá")
    yield connection
    connection.rollback()
    connection.close()


def run(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def scalar(conn, sql):
    return run(conn, sql)[0][0]


def test_five_queries_exist_and_return_rows(conn):
    queries = load_queries()
    assert set(queries) == {"rollup", "drilldown", "slice", "dice", "pivot", "pivot_hour", "dice_category", "mismatch"}
    for name, sql in queries.items():
        assert run(conn, sql), f"truy vấn {name} không ra dòng nào"


def test_rollup_levels_add_up(conn):
    rows = run(conn, load_queries()["rollup"])  # (year, quarter, month, review_count, avg_rating)
    total = scalar(conn, "SELECT count(*) FROM dw.fact_review")
    months = [r for r in rows if r[2] is not None]
    quarters = [r for r in rows if r[2] is None and r[1] is not None]
    years = [r for r in rows if r[1] is None and r[0] is not None]
    grand = [r for r in rows if r[0] is None]
    assert len(grand) == 1 and grand[0][3] == total
    for q in quarters:
        assert q[3] == sum(m[3] for m in months if (m[0], m[1]) == (q[0], q[1]))
    for y in years:
        assert y[3] == sum(q[3] for q in quarters if q[0] == y[0])
    assert sum(y[3] for y in years) == total


def test_drilldown_group_equals_sum_of_platforms(conn):
    rows = run(conn, load_queries()["drilldown"])  # (group, platform, count, avg, is_group_subtotal)
    total = scalar(conn, "SELECT count(*) FROM dw.fact_review")
    platforms = [r for r in rows if r[1] is not None]
    groups = [r for r in rows if r[1] is None and r[0] is not None]
    assert [r for r in rows if r[0] is None][0][2] == total
    for g in groups:
        assert g[2] == sum(p[2] for p in platforms if p[0] == g[0])
    assert sum(g[2] for g in groups) == total


def test_slice_matches_independent_count(conn):
    rows = run(conn, load_queries()["slice"])
    expected = scalar(conn, "SELECT count(*) FROM dw.fact_review f JOIN dw.dim_time t USING (time_key) WHERE t.year = 2025")
    assert sum(r[1] for r in rows) == expected > 0


def test_dice_matches_independent_count(conn):
    rows = run(conn, load_queries()["dice"])
    expected = scalar(conn, """
        SELECT count(*) FROM dw.fact_review f
        WHERE f.time_key BETWEEN 20240101 AND 20251231
          AND f.platform_key IN (SELECT platform_key FROM dw.dim_platform WHERE platform_group = 'trong_nuoc')
          AND f.source_key IN (SELECT source_key FROM dw.dim_source WHERE source_type = 'kho_ung_dung')""")
    assert sum(r[2] for r in rows) == expected > 0


def test_pivot_columns_add_up(conn):
    rows = run(conn, load_queries()["pivot"])  # (platform, tich_cuc, trung_tinh, tieu_cuc, tong)
    assert all(r[1] + r[2] + r[3] == r[4] for r in rows)
    assert sum(r[4] for r in rows) == scalar(conn, "SELECT count(rating) FROM dw.fact_review")


def test_pivot_hour_matches_independent_count(conn):
    rows = run(conn, load_queries()["pivot_hour"])  # (day_part, tich_cuc, trung_tinh, tieu_cuc, tong)
    assert all(r[1] + r[2] + r[3] == r[4] for r in rows)
    assert sum(r[4] for r in rows) == scalar(conn, "SELECT count(*) FROM dw.fact_review WHERE rating IS NOT NULL AND hour_key IS NOT NULL")


def test_dice_category_matches_independent_count(conn):
    rows = run(conn, load_queries()["dice_category"])
    if not rows:
        pytest.skip("dim_platform.category chưa nạp (python src/etl/load/load_platform_attributes.py)")
    expected = scalar(conn, """
        SELECT count(*) FROM dw.fact_review f
        WHERE f.time_key >= 20220101
          AND f.platform_key IN (SELECT platform_key FROM dw.dim_platform WHERE category IS NOT NULL)""")
    assert sum(r[2] for r in rows) == expected


def test_mismatch_counts_consistent(conn):
    rows = run(conn, load_queries()["mismatch"])  # (platform, labeled, mismatch, rate)
    assert rows and all(r[2] <= r[1] for r in rows)
    assert sum(r[1] for r in rows) == scalar(conn, "SELECT count(is_mismatch) FROM dw.fact_review")
