"""Kiểm thử G12 (load_trends.py): đọc tệp Google Trends và nạp vào clean.trends_monthly.

Phần đọc tệp không cần CSDL. Phần CSDL bỏ qua khi chưa kết nối được hoặc chưa áp migration 0007; mọi thay đổi được hoàn tác.
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

import pytest

ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL_DIR))
sys.path.insert(0, str(ETL_DIR / "load"))

from common import connect  # noqa: E402
from load_trends import load_trends, read_trends  # noqa: E402

SOLO = ["month", "platform", "keyword", "interest_self_scaled", "is_partial", "platform_group"]
ANCHOR = ["month", "platform", "keyword", "interest_scaled_to_anchor", "interest_self_scaled", "is_partial",
          "platform_group"]


def _write(path: Path, fields: list[str], rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_read_solo_file_leaves_anchor_empty(tmp_path):
    path = _write(tmp_path / "t.csv", SOLO, [
        {"month": "2026-10", "platform": "ELSA Speak", "keyword": "ELSA Speak", "interest_self_scaled": "41",
         "is_partial": "False", "platform_group": "trong_nuoc"},
        {"month": "2026-11", "platform": "ELSA Speak", "keyword": "ELSA Speak", "interest_self_scaled": "20",
         "is_partial": "True", "platform_group": "trong_nuoc"},
    ])
    rows = read_trends(path)
    assert rows[0]["month"] == date(2026, 10, 1) and rows[0]["interest_self_scaled"] == 41.0
    assert rows[0]["interest_scaled_to_anchor"] is None and rows[0]["is_partial"] is False
    assert rows[1]["is_partial"] is True


def test_read_anchor_file_and_duplicates_keep_last(tmp_path):
    path = _write(tmp_path / "t.csv", ANCHOR, [
        {"month": "2026-10", "platform": "DUOLINGO", "keyword": "Duolingo", "interest_scaled_to_anchor": "100",
         "interest_self_scaled": "90", "is_partial": "False", "platform_group": "quoc_te"},
        {"month": "2026-10", "platform": "DUOLINGO", "keyword": "Duolingo", "interest_scaled_to_anchor": "95.5",
         "interest_self_scaled": "88", "is_partial": "False", "platform_group": "quoc_te"},
    ])
    rows = read_trends(path)
    assert len(rows) == 1 and rows[0]["interest_scaled_to_anchor"] == 95.5


@pytest.mark.parametrize("bad", [{"interest_self_scaled": "120"}, {"month": "thang-10"}, {"platform": ""}])
def test_read_rejects_bad_rows(tmp_path, bad):
    row = {"month": "2026-10", "platform": "Busuu", "keyword": "Busuu", "interest_self_scaled": "10",
           "is_partial": "False", "platform_group": "quoc_te", **bad}
    with pytest.raises(ValueError):
        read_trends(_write(tmp_path / "t.csv", SOLO, [row]))


def test_read_rejects_missing_columns(tmp_path):
    with pytest.raises(ValueError, match="Thiếu cột"):
        read_trends(_write(tmp_path / "t.csv", ["month", "platform"], [{"month": "2026-10", "platform": "X"}]))


@pytest.fixture()
def conn():
    try:
        connection = connect(connect_timeout=3)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Không kết nối được PostgreSQL cục bộ: {type(exc).__name__}")
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass('clean.trends_monthly') IS NOT NULL")
        if not cur.fetchone()[0]:
            connection.close()
            pytest.skip("Chưa chạy migration 0007")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_load_is_idempotent_and_overwrites_resampled_values(conn):
    row = {"month": date(1990, 1, 1), "platform_name": "ELSA Speak", "keyword": "ELSA Speak",
           "interest_self_scaled": 40.0, "interest_scaled_to_anchor": None, "is_partial": False,
           "platform_group": "trong_nuoc"}
    first = load_trends(conn, [row, {**row, "platform_name": "Nền tảng lạ"}])
    assert first["inserted"] == 2 and first["unknown_platforms"] == ["Nền tảng lạ"]
    second = load_trends(conn, [{**row, "interest_self_scaled": 42.0}])
    assert second["inserted"] == 0 and second["updated"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT interest_self_scaled FROM clean.trends_monthly "
                    "WHERE month = '1990-01-01' AND platform_name = 'ELSA Speak'")
        assert float(cur.fetchone()[0]) == 42.0
