"""Kiểm thử M3 trên chuỗi tổng hợp (không cần CSDL): walk-forward không nhìn tương lai, chỉ số, khoảng tin cậy hợp lệ."""

import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import m3_forecast as m3  # noqa: E402


def _panel(n_platforms=4, n_months=40):
    rng = np.random.default_rng(m3.SEED)
    panel = {}
    for p in range(n_platforms):
        series, nr = [], 0.3 + 0.05 * p
        for i in range(n_months):
            nr = min(max(nr + rng.normal(0, 0.03), 0.02), 0.9)
            month = date(2021 + i // 12, i % 12 + 1, 1)
            series.append({"month": month, "n": 40 + int(rng.integers(0, 30)), "positive_rate": 1 - nr - 0.1,
                           "negative_rate": nr, "avg_rating": 4 - 2 * nr, "sentiment_index": 100 * (1 - 2 * nr - 0.1)})
        panel[f"P{p}"] = series
    return panel


def test_ridge_recovers_linear_relation():
    X = np.random.default_rng(1).normal(size=(200, 3))
    y = X @ np.array([2.0, -1.0, 0.5]) + 3
    pred = m3.ridge_fit_predict(X, y, X[:5], alpha=1e-6)
    assert np.allclose(pred, y[:5], atol=1e-3)


def test_walk_forward_trains_only_on_earlier_months(monkeypatch):
    rows = m3.build_rows(_panel(), [])
    seen = []
    real = m3.ridge_fit_predict

    def spy(X_train, y_train, X_test, alpha=m3.ALPHA):
        seen.append(len(X_train))
        return real(X_train, y_train, X_test, alpha)

    monkeypatch.setattr(m3, "ridge_fit_predict", spy)
    preds = m3.walk_forward(rows, "negative_rate", m3.FULL_CONFIG, date(2023, 1, 1))
    assert preds and all(p["month"] >= date(2023, 1, 1) for p in preds)
    for p, size in zip(sorted({q["month"] for q in preds}), seen):
        assert size == sum(1 for r in rows if r.month < p)  # đúng số dòng trước tháng kiểm định, không dòng nào sau


def test_event_columns_constant_when_no_events_so_configs_match():
    rows = m3.build_rows(_panel(), [])
    a = m3.walk_forward(rows, "negative_rate", "C2_co_cam_xuc", date(2023, 1, 1))
    b = m3.walk_forward(rows, "negative_rate", "C4_co_cam_xuc_va_su_kien", date(2023, 1, 1))
    assert [round(x["pred"], 9) for x in a] == [round(x["pred"], 9) for x in b]


def test_metrics_values():
    res = m3.metrics([1, 2, 3], [1, 3, 5], [0, 4, 4])
    assert res["MAE"] == 1.0 and res["n"] == 3 and abs(res["RMSE"] - round((5 / 3) ** 0.5, 4)) < 1e-4
    assert res["dung_chieu"] == round(2 / 3, 4)


def test_forecast_rows_valid_for_both_targets():
    rows = m3.build_rows(_panel(), [], with_future=True)
    forecasts = m3.build_forecasts(rows)
    assert {f["target"] for f in forecasts} == set(m3.TARGETS)
    for f in forecasts:
        assert f["lo"] <= f["value"] <= f["hi"]
        if f["target"] == "negative_rate":
            assert 0 <= f["lo"] and f["hi"] <= 1
    future = [f for f in forecasts if f["actual"] is None]
    assert len(future) == 2 * 4 and all(f["month"] == date(2024, 5, 1) for f in future)
