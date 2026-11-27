"""Phát hiện bất thường tỷ lệ tiêu cực theo kỳ hai tuần và ghi cảnh báo vào dw.fact_alert (N4).

Quy tắc và ngưỡng: config/anomaly.yml, mã lõi: src/backend/app/services/anomaly.py.
Chạy lại không sinh cảnh báo trùng cho cùng (nền tảng, kỳ, chỉ số). time_key = ngày đầu kỳ hai tuần.
Đề xuất hành động và bộ phận phụ trách do bước khác ghép, script này chỉ phát hiện và ghi.

    python src/etl/detect_anomaly.py [--dry-run] [--platform TEN] [--all]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ETL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ETL_DIR))
sys.path.insert(0, str(ETL_DIR.parent / "backend"))

from app.services.anomaly import attach_events, detect, fetch_series, load_config  # noqa: E402
from common import connect  # noqa: E402


def write_alerts(conn, cfg: dict, platform: str | None = None, all_periods: bool = False) -> dict:
    """Ghi cảnh báo mới; hàm không commit. Trả về số kỳ xét, số bất thường, số cảnh báo mới ghi."""
    metric = cfg["metric_name"]
    summary = {"series": 0, "anomalies": 0, "inserted": 0, "skipped_short": [], "found": []}
    for name, series in sorted(fetch_series(conn, platform).items()):
        results = detect(series, cfg["window"], cfg["k"], cfg["min_delta"], cfg["min_reviews"])
        summary["series"] += 1
        if len(results) <= cfg["window"]:
            summary["skipped_short"].append(f"{name} ({len(results)} kỳ)")
            continue
        attach_events(conn, name, results)
        recent = results if all_periods else results[-cfg["recent_periods_to_alert"]:]
        for res in recent:
            if not res.is_anomaly:
                continue
            summary["anomalies"] += 1
            summary["found"].append((name, res.period_start.isoformat(), round(res.value, 4), res.events))
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dw.fact_alert (time_key, platform_key, metric_name, metric_value, threshold, detected_at, status)
                    SELECT t.time_key, p.platform_key, %s, %s, %s, %s, 'moi'
                    FROM dw.dim_platform p JOIN dw.dim_time t ON t.full_date = %s
                    WHERE p.platform_name = %s
                      AND NOT EXISTS (SELECT 1 FROM dw.fact_alert a
                                      WHERE a.platform_key = p.platform_key AND a.time_key = t.time_key
                                        AND a.metric_name = %s)
                    """,
                    (metric, round(res.value, 4), round(res.threshold, 4), datetime.now(timezone.utc),
                     res.period_start, name, metric),
                )
                summary["inserted"] += cur.rowcount
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phát hiện bất thường và ghi dw.fact_alert")
    parser.add_argument("--dry-run", action="store_true", help="tính rồi hoàn tác, không ghi")
    parser.add_argument("--platform", help="chỉ một nền tảng (mặc định tất cả)")
    parser.add_argument("--all", action="store_true", help="ghi cảnh báo cho mọi kỳ lịch sử, không chỉ các kỳ gần nhất")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cfg = load_config()
    with connect() as conn:
        summary = write_alerts(conn, cfg, args.platform, args.all)
        conn.rollback() if args.dry_run else conn.commit()
    print(f"Chuỗi xét: {summary['series']}, bất thường: {summary['anomalies']}, cảnh báo mới ghi: {summary['inserted']}"
          f"{' (dry-run, đã hoàn tác)' if args.dry_run else ''}")
    for item in summary["skipped_short"]:
        print("Không tính (dưới", cfg["window"] + 1, "kỳ):", item)
    for name, start, value, events in summary["found"]:
        print(f"  {name} kỳ {start}: tỷ lệ tiêu cực {value}" + (f" | trùng sự kiện: {'; '.join(events)}" if events else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
