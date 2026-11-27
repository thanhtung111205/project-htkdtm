"""Kiểm thử G22 (nhật ký vào dw.etl_run_log) và G23 (bước sau ETL, dữ liệu bối cảnh) của run_pipeline.py.

Ca CSDL tự bỏ qua khi chưa kết nối được PostgreSQL; mọi thay đổi trong ca được hoàn tác.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ETL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ETL_DIR))
sys.path.insert(0, str(ETL_DIR / "load"))

import run_pipeline  # noqa: E402
from common import connect  # noqa: E402
from load_run_log import backfill, steps_from_entry, write_steps  # noqa: E402

NOW = datetime(2026, 11, 26, 19, 0, tzinfo=timezone.utc).isoformat()


@pytest.fixture()
def conn():
    try:
        connection = connect(connect_timeout=3)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Không kết nối được PostgreSQL cục bộ: {type(exc).__name__}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _count(conn, run_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dw.etl_run_log WHERE run_id = %s", (run_id,))
        return cur.fetchone()[0]


def test_steps_from_entry_maps_summary_to_four_steps() -> None:
    entry = {"run_id": "x", "started_at": NOW, "finished_at": NOW, "status": "success",
             "summary": {"collectors_total": 18, "collectors_failed": 0, "raw_read": 10, "raw_inserted": 4,
                         "clean_inserted": 4, "clean_dropped_empty": 0, "fact_inserted": 4, "fact_total": 100}}
    steps = steps_from_entry(entry)
    assert [s["step"] for s in steps] == ["collect", "raw", "clean", "dw"]
    assert steps[1]["rows_inserted"] == 4 and all(s["status"] == "success" for s in steps)


def test_steps_from_failed_entry_keeps_error() -> None:
    steps = steps_from_entry({"run_id": "x", "started_at": NOW, "status": "failed", "error": "boom", "summary": {}})
    assert len(steps) == 1 and steps[0]["status"] == "failed" and steps[0]["error"] == "boom"


def test_write_steps_rejects_unknown_step(conn) -> None:
    with pytest.raises(ValueError):
        write_steps(conn, "t-bad", [{"step": "khong_co", "status": "success", "started_at": NOW}])


def test_write_steps_is_idempotent_per_run(conn) -> None:
    steps = [{"step": "raw", "status": "success", "started_at": NOW, "finished_at": NOW, "rows_read": 3, "rows_inserted": 2},
             {"step": "score", "status": "failed", "started_at": NOW, "error": "x" * 2000}]
    assert write_steps(conn, "t-run-1", steps) == 2
    assert write_steps(conn, "t-run-1", steps) == 2
    assert _count(conn, "t-run-1") == 2
    with conn.cursor() as cur:
        cur.execute("SELECT length(error_message) FROM dw.etl_run_log WHERE run_id = 't-run-1' AND step = 'score'")
        assert cur.fetchone()[0] == 1000


def test_backfill_reads_jsonl_and_skips_bad_lines(conn, tmp_path) -> None:
    good = {"run_id": "t-bf-1", "started_at": NOW, "finished_at": NOW, "status": "success",
            "summary": {"collectors_total": 2, "collectors_failed": 0, "raw_read": 1, "raw_inserted": 1,
                        "clean_inserted": 1, "clean_dropped_empty": 0, "fact_inserted": 1, "fact_total": 5}}
    path = tmp_path / "pipeline_runs.jsonl"
    path.write_text(json.dumps(good) + "\nkhông phải json\n" + json.dumps({"thieu": "khoa"}) + "\n", encoding="utf-8")
    assert backfill(conn, path) == {"runs": 1, "steps": 4}
    assert backfill(conn, path) == {"runs": 1, "steps": 4}
    assert _count(conn, "t-bf-1") == 4


def test_backfill_missing_file_is_noop(conn, tmp_path) -> None:
    assert backfill(conn, tmp_path / "khong_co.jsonl") == {"runs": 0, "steps": 0}


def test_post_steps_skip_scoring_without_model_and_build_platform_period(conn, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(run_pipeline, "MODEL_DIR", tmp_path / "khong_co_mo_hinh")

    class NoCommit:   # dùng kết nối của ca kiểm thử nhưng không cho commit, để không ghi vào CSDL thật
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return conn.cursor()

        def commit(self):
            pass

    monkeypatch.setattr(run_pipeline, "connect", lambda *a, **k: NoCommit())
    steps: list[dict] = []
    failures = run_pipeline.run_post_steps(argparse.Namespace(env_file=None), steps)
    assert failures == 0
    assert [s["step"] for s in steps] == ["platform_period"] and steps[0]["status"] == "success"


def test_cycle_dry_run_does_not_write_run_log_or_post_steps(tmp_path, monkeypatch, conn) -> None:
    monkeypatch.setenv("EDUVISION_LOG_DIR", str(tmp_path / "logs"))
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    assert run_pipeline.main(["--skip-collect", "--dry-run", "--incoming", str(incoming)]) == 0
    entry = json.loads((tmp_path / "logs" / "pipeline_runs.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert entry["summary"]["post_failures"] == 0
    assert _count(conn, entry["run_id"]) == 0
