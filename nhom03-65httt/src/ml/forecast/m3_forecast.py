"""M3: dự báo Sentiment Index và tỷ lệ tiêu cực (negative_rate) của từng nền tảng cho THÁNG KẾ TIẾP.

Đọc dw.fact_platform_period (không tự tính lại cảm xúc: đổi sang nhãn M1 thì chỉ cần dựng lại bảng đó), chỉ lấy tháng có
từ MIN_REVIEWS đánh giá. Một mô hình hồi quy Ridge dùng chung cho mọi nền tảng, chuẩn hóa đặc trưng, tự cài bằng numpy
(chưa dùng LightGBM vì chuỗi chỉ khoảng 30 đến 40 tháng mỗi nền tảng, mô hình có điều chuẩn phù hợp hơn). Không có thành phần
ngẫu nhiên; hạt ngẫu nhiên SEED chỉ được ghi lại trong kết quả để mô tả cách tái tạo.

Đánh giá walk-forward theo tháng: với mỗi tháng kiểm định m, huấn luyện CHỈ trên các dòng có tháng < m rồi dự báo tháng m.
Baseline: "kỳ sau giống kỳ này" (last) và trung bình trượt 3 kỳ (ma3). Chỉ số: MAE, RMSE, tỷ lệ đúng chiều.
Thí nghiệm E4: 4 cấu hình có/không đặc trưng cảm xúc và sự kiện.

    python src/ml/forecast/m3_forecast.py evaluate            # in kết quả E4, lưu models/e4_results.json (ngoài Git)
    python src/ml/forecast/m3_forecast.py write [--dry-run]   # huấn luyện cấu hình đầy đủ, ghi dw.fact_forecast
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src" / "etl"))

SEED = 42
MIN_REVIEWS = 30          # tháng có dưới ngưỡng này bị bỏ (đề cương: tháng từ 30 đánh giá)
MIN_SERIES_ROWS = 24      # nền tảng có ít tháng đủ điều kiện hơn thì không dự báo (DUOLINGO, Khan Academy)
MIN_TRAIN_ROWS = 30
ALPHA = 1.0               # độ điều chuẩn Ridge, cố định (không dò theo tập kiểm định để tránh rò rỉ)
TEST_START = date(2024, 1, 1)
TARGETS = {"sentiment_index": "M3_sentiment_index", "negative_rate": "M3_negative_rate"}
CONFIGS = {  # tên: (đặc trưng cảm xúc, đặc trưng sự kiện)
    "C1_khong_cam_xuc_khong_su_kien": (False, False),
    "C2_co_cam_xuc": (True, False),
    "C3_co_su_kien": (False, True),
    "C4_co_cam_xuc_va_su_kien": (True, True),
}
FULL_CONFIG = "C4_co_cam_xuc_va_su_kien"


@dataclass
class Row:
    platform: str
    month: date
    y: dict            # giá trị thật của hai mục tiêu (None nếu là dòng dự báo tương lai)
    sent: dict         # đặc trưng cảm xúc theo mục tiêu; ba phần tử đầu là lag1..3, phần tử thứ tư là trung bình 3 kỳ
    other: list        # đặc trưng không phải cảm xúc: số đánh giá, mùa vụ
    event: list        # đặc trưng sự kiện


def load_panel(conn) -> dict[str, list[dict]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.platform_name, t.full_date, f.new_review_count, f.positive_rate, f.negative_rate,
                   f.avg_rating, f.sentiment_index
            FROM dw.fact_platform_period f
            JOIN dw.dim_platform p USING (platform_key) JOIN dw.dim_time t USING (time_key)
            WHERE f.new_review_count >= %s ORDER BY p.platform_name, t.full_date
            """,
            (MIN_REVIEWS,),
        )
        panel: dict[str, list[dict]] = {}
        for name, month, n, pos, neg, rating, si in cur.fetchall():
            if None in (pos, neg, rating, si):  # tháng không có đánh giá có sao (chỉ bình luận YouTube) thì bỏ
                continue
            panel.setdefault(name, []).append({"month": month, "n": n, "positive_rate": float(pos),
                                               "negative_rate": float(neg), "avg_rating": float(rating),
                                               "sentiment_index": float(si)})
    return panel


def load_events(conn) -> list[tuple[str | None, date, date]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.platform_name, e.start_date, coalesce(e.end_date, e.start_date) "
            "FROM dw.dim_event e LEFT JOIN dw.dim_platform p USING (platform_key)"
        )
        return cur.fetchall()


def _next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _events_in_month(events, platform: str, month: date) -> int:
    end = _next_month(month)
    return sum(1 for name, s, e in events if (name is None or name == platform) and s < end and e >= month)


def _make_row(platform, series, i, month, events) -> Row:
    """Dòng đặc trưng cho tháng `month` chỉ dựa trên các tháng trước series[:i] (không dùng thông tin tháng này)."""
    prev = series[:i]
    y = {k: series[i][k] for k in TARGETS} if i < len(series) else {k: None for k in TARGETS}
    sent = {}
    for key, other_key, scale in (("sentiment_index", "negative_rate", 1.0), ("negative_rate", "sentiment_index", 0.01)):
        lags = [prev[-j][key] for j in (1, 2, 3)]
        sent[key] = lags + [sum(lags) / 3, prev[-1]["avg_rating"], prev[-1]["positive_rate"], prev[-1][other_key] * scale]
    other = [math.log1p(prev[-1]["n"]), math.log1p(prev[-2]["n"]),
             math.sin(2 * math.pi * month.month / 12), math.cos(2 * math.pi * month.month / 12)]
    event = [_events_in_month(events, platform, month), _events_in_month(events, platform, prev[-1]["month"])]
    return Row(platform, month, y, sent, other, event)


def build_rows(panel, events, with_future=False) -> list[Row]:
    rows = []
    for name, series in panel.items():
        for i in range(3, len(series)):
            rows.append(_make_row(name, series, i, series[i]["month"], events))
        if with_future and len(series) >= MIN_SERIES_ROWS:
            rows.append(_make_row(name, series, len(series), _next_month(series[-1]["month"]), events))
    return rows


def features(row: Row, target: str, config: str) -> list[float]:
    use_sent, use_event = CONFIGS[config]
    return row.other + (row.sent[target] if use_sent else []) + (row.event if use_event else [])


def ridge_fit_predict(X_train, y_train, X_test, alpha=ALPHA):
    X, y, Xt = np.asarray(X_train, float), np.asarray(y_train, float), np.asarray(X_test, float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-9] = 1.0                      # cột hằng (ví dụ sự kiện còn trống) không đóng góp gì
    Z, Zt = (X - mu) / sd, (Xt - mu) / sd
    ym = y.mean()
    w = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return Zt @ w + ym


def metrics(pred, actual, last) -> dict:
    pred, actual, last = (np.asarray(a, float) for a in (pred, actual, last))
    err = pred - actual
    return {"n": int(len(actual)), "MAE": round(float(np.abs(err).mean()), 4),
            "RMSE": round(float(math.sqrt((err ** 2).mean())), 4),
            "dung_chieu": round(float((np.sign(pred - last) == np.sign(actual - last)).mean()), 4)}


def walk_forward(rows: list[Row], target: str, config: str, test_start: date = TEST_START) -> list[dict]:
    """Mỗi tháng kiểm định m: huấn luyện trên dòng có tháng < m, dự báo các dòng tháng m. Trả danh sách dự báo."""
    out = []
    for m in sorted({r.month for r in rows if r.month >= test_start}):
        train = [r for r in rows if r.month < m]
        test = [r for r in rows if r.month == m]
        if len(train) < MIN_TRAIN_ROWS:
            continue
        pred = ridge_fit_predict([features(r, target, config) for r in train], [r.y[target] for r in train],
                                 [features(r, target, config) for r in test])
        for r, p in zip(test, pred):
            out.append({"platform": r.platform, "month": r.month, "pred": float(p), "actual": r.y[target],
                        "last": r.sent[target][0], "ma3": r.sent[target][3]})
    return out


def evaluate(rows: list[Row]) -> dict:
    result = {"seed": SEED, "alpha": ALPHA, "test_start": TEST_START.isoformat(), "min_reviews": MIN_REVIEWS,
              "run_at": datetime.now(timezone.utc).isoformat(), "targets": {}}
    for target in TARGETS:
        entry = {}
        for config in CONFIGS:
            preds = walk_forward(rows, target, config)
            entry[config] = metrics([p["pred"] for p in preds], [p["actual"] for p in preds], [p["last"] for p in preds])
        base = walk_forward(rows, target, FULL_CONFIG)  # cùng tập kiểm định cho hai baseline
        actual, last = [p["actual"] for p in base], [p["last"] for p in base]
        entry["baseline_last"] = metrics(last, actual, last)
        entry["baseline_ma3"] = metrics([p["ma3"] for p in base], actual, last)
        result["targets"][target] = entry
    return result


def clip(target: str, v: float) -> float:
    lo, hi = (0.0, 1.0) if target == "negative_rate" else (-100.0, 100.0)
    return min(max(v, lo), hi)


def build_forecasts(rows_with_future: list[Row]) -> list[dict]:
    """Dòng ghi vào fact_forecast: dự báo walk-forward có số thực tế, cộng dự báo tháng kế tiếp (actual rỗng)."""
    out = []
    history = [r for r in rows_with_future if r.y["sentiment_index"] is not None]
    future = [r for r in rows_with_future if r.y["sentiment_index"] is None]
    for target in TARGETS:
        wf = walk_forward(history, target, FULL_CONFIG)
        sigma = float(np.std([p["pred"] - p["actual"] for p in wf], ddof=1))  # khoảng tin cậy 95 phần trăm theo sai số walk-forward
        for p in wf:
            lo, hi = sorted((clip(target, p["pred"] - 1.96 * sigma), clip(target, p["pred"] + 1.96 * sigma)))
            out.append({"target": target, "platform": p["platform"], "month": p["month"],
                        "value": clip(target, p["pred"]), "lo": lo, "hi": hi, "actual": p["actual"]})
        pred = ridge_fit_predict([features(r, target, FULL_CONFIG) for r in history], [r.y[target] for r in history],
                                 [features(r, target, FULL_CONFIG) for r in future])
        for r, v in zip(future, pred):
            lo, hi = sorted((clip(target, v - 1.96 * sigma), clip(target, v + 1.96 * sigma)))
            out.append({"target": target, "platform": r.platform, "month": r.month, "value": clip(target, float(v)),
                        "lo": lo, "hi": hi, "actual": None})
    return out


def write_forecasts(conn, forecasts: list[dict]) -> int:
    """Upsert vào dw.fact_forecast; hàm không commit. Chạy lại cho cùng kết quả."""
    with conn.cursor() as cur:
        cur.execute("SELECT model_name, model_key FROM dw.dim_model WHERE model_name = ANY(%s) AND model_version = 'v0'",
                    (list(TARGETS.values()),))
        model_keys = dict(cur.fetchall())
        if len(model_keys) != len(TARGETS):
            raise RuntimeError("Thiếu dòng dim_model M3_sentiment_index / M3_negative_rate (chạy migration 0004)")
        cur.execute("SELECT platform_name, platform_key FROM dw.dim_platform")
        platform_keys = dict(cur.fetchall())
        for f in forecasts:
            d = f["month"]
            time_key = int(d.strftime("%Y%m%d"))
            cur.execute(
                "INSERT INTO dw.dim_time (time_key, full_date, week, month, quarter, year) "
                "VALUES (%s, %s, extract(week FROM %s::date), extract(month FROM %s::date), "
                "extract(quarter FROM %s::date), extract(year FROM %s::date)) ON CONFLICT (time_key) DO NOTHING",
                (time_key, d, d, d, d, d),
            )
            cur.execute(
                """
                INSERT INTO dw.fact_forecast (platform_key, time_key, model_key, forecast_value, ci_lower, ci_upper, actual_value)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (platform_key, time_key, model_key) DO UPDATE
                SET forecast_value = EXCLUDED.forecast_value, ci_lower = EXCLUDED.ci_lower,
                    ci_upper = EXCLUDED.ci_upper, actual_value = EXCLUDED.actual_value
                """,
                (platform_keys[f["platform"]], time_key, model_keys[TARGETS[f["target"]]],
                 round(f["value"], 4), round(f["lo"], 4), round(f["hi"], 4),
                 None if f["actual"] is None else round(f["actual"], 4)),
            )
    return len(forecasts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="M3 dự báo, thí nghiệm E4 và ghi fact_forecast")
    parser.add_argument("command", choices=["evaluate", "write"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from common import connect

    with connect() as conn:
        panel, events = load_panel(conn), load_events(conn)
        long_panel = {k: v for k, v in panel.items() if len(v) >= MIN_SERIES_ROWS}
        if args.command == "evaluate":
            res = evaluate(build_rows(long_panel, events))
            res["rows_per_platform"] = {k: len(v) for k, v in panel.items()}
            res["events_in_dim_event"] = len(events)
            (ROOT / "models").mkdir(exist_ok=True)
            (ROOT / "models" / "e4_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        skipped = sorted(set(panel) - set(long_panel))
        written = write_forecasts(conn, build_forecasts(build_rows(long_panel, events, with_future=True)))
        conn.rollback() if args.dry_run else conn.commit()
        print(f"Đã ghi {written} dòng fact_forecast{' (dry-run, hoàn tác)' if args.dry_run else ''}; "
              f"không dự báo do chuỗi ngắn: {', '.join(skipped) or 'không có'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
