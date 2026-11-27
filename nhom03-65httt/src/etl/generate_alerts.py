"""T7: sinh cảnh báo và khuyến nghị tự động vào dw.fact_alert.

Hai bước, cùng một giao dịch:
  1. Phát hiện bất thường tỷ lệ tiêu cực theo kỳ hai tuần (N4, detect_anomaly.write_alerts): chỉ kỳ đã kết thúc,
     bắt đầu trong 28 ngày gần đây; chạy lại không sinh trùng.
  2. Điền recommended_action (đề xuất hành động kèm số liệu dẫn chứng) và responsible_department cho MỌI cảnh báo
     còn trống hai cột này, kể cả cảnh báo do bước khác ghi. Bảng ánh xạ: config/recommendations.yml.

Workflow n8n 03 đọc hai cột này để đưa vào email cảnh báo. run_pipeline.py gọi run() sau khi tổng hợp fact_platform_period.

    python src/etl/generate_alerts.py [--dry-run] [--skip-detect]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

ETL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ETL_DIR))

from common import connect, project_root  # noqa: E402
from detect_anomaly import load_config, write_alerts  # noqa: E402

RULES_FILE = project_root() / "config" / "recommendations.yml"
BIWEEKLY_METRICS = {"negative_rate_2w"}  # time_key của các chỉ số này là ngày đầu kỳ hai tuần


def load_rules(path: Path = RULES_FILE) -> dict:
    rules = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("aspects", "metrics", "default"):
        rules.setdefault(key, {})
    rules.setdefault("dominant_share", 0.4)
    rules.setdefault("min_aspect_mentions", 5)
    rules.setdefault("escalate_delta", 0.15)
    return rules


def _pct(value: float) -> str:
    return f"{value * 100:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


def _vn_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def alert_period(metric: str, day: date) -> tuple[date, date]:
    return (day, day + timedelta(days=13)) if metric in BIWEEKLY_METRICS else (day, day)


def choose_rule(rules: dict, metric: str, alert_aspect: str | None, dominant: tuple[str, float, int] | None) -> tuple[dict, str]:
    """Chọn mục ánh xạ theo thứ tự: khía cạnh của cảnh báo, khía cạnh chiếm ưu thế, chỉ số, mặc định."""
    if alert_aspect and alert_aspect in rules["aspects"]:
        return rules["aspects"][alert_aspect], f"khía cạnh {alert_aspect}"
    if dominant:
        name, share, mentions = dominant
        if (name in rules["aspects"] and share >= rules["dominant_share"]
                and mentions >= rules["min_aspect_mentions"]):
            return rules["aspects"][name], f"khía cạnh {name} chiếm {_pct(share)} lượt nhắc tiêu cực"
    if metric in rules["metrics"]:
        return rules["metrics"][metric], f"chỉ số {metric}"
    return rules["default"], "mặc định"


def build_recommendation(rules: dict, alert: dict, evidence: dict) -> tuple[str, str]:
    """Trả về (recommended_action, responsible_department). Hàm thuần, không cần CSDL."""
    start, end = alert_period(alert["metric_name"], alert["day"])
    period = _vn_date(start) if start == end else f"{_vn_date(start)} đến {_vn_date(end)}"
    rule, _ = choose_rule(rules, alert["metric_name"], alert.get("aspect_name"), evidence.get("dominant"))
    text = rule["action"].format(platform=alert["platform_name"], period=period, metric=alert["metric_name"]).strip()

    value, threshold = float(alert["metric_value"]), float(alert["threshold"])
    is_rate = "rate" in alert["metric_name"]
    if is_rate and evidence.get("reviews"):
        proof = (f"tỷ lệ tiêu cực {_pct(value)} ({evidence['negative']}/{evidence['reviews']} đánh giá có sao), "
                 f"ngưỡng {_pct(threshold)}")
    else:
        proof = f"{alert['metric_name']} = {value:g}, ngưỡng {threshold:g}"
    if evidence.get("dominant"):
        name, share, mentions = evidence["dominant"]
        proof += f"; khía cạnh bị chê nhiều nhất: {name} ({_pct(share)} của {mentions} lượt nhắc tiêu cực)"
    text += f" Dẫn chứng: {proof}."
    if is_rate and value - threshold >= rules["escalate_delta"]:
        text += " Mức vượt ngưỡng cao: báo cáo Ban điều hành."
    return text, rule["department"]


def gather_evidence(conn, alert: dict) -> dict:
    """Số đánh giá có sao, số tiêu cực (1 đến 2 sao) và khía cạnh tiêu cực chiếm ưu thế trong kỳ của cảnh báo."""
    start, end = alert_period(alert["metric_name"], alert["day"])
    lo, hi = int(start.strftime("%Y%m%d")), int(end.strftime("%Y%m%d"))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), count(*) FILTER (WHERE rating <= 2) FROM dw.fact_review "
            "WHERE platform_key = %s AND time_key BETWEEN %s AND %s AND rating IS NOT NULL",
            (alert["platform_key"], lo, hi),
        )
        reviews, negative = cur.fetchone()
        cur.execute(
            """
            SELECT d.aspect_name, count(*) FROM dw.fact_review_aspect a JOIN dw.dim_aspect d USING (aspect_key)
            WHERE a.platform_key = %s AND a.time_key BETWEEN %s AND %s AND a.sentiment_label = 'tieu_cuc'
            GROUP BY d.aspect_name ORDER BY count(*) DESC, d.aspect_name
            """,
            (alert["platform_key"], lo, hi),
        )
        mentions = cur.fetchall()
    total = sum(n for _, n in mentions)
    dominant = (mentions[0][0], mentions[0][1] / total, total) if total else None
    return {"reviews": reviews, "negative": negative, "dominant": dominant}


def fill_recommendations(conn, rules: dict) -> int:
    """Điền hai cột cho mọi cảnh báo còn trống; hàm không commit. Trả về số cảnh báo đã điền."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.alert_key, a.metric_name, a.metric_value, a.threshold, a.platform_key, p.platform_name,
                   t.full_date, asp.aspect_name
            FROM dw.fact_alert a
            JOIN dw.dim_platform p USING (platform_key)
            JOIN dw.dim_time t USING (time_key)
            LEFT JOIN dw.dim_aspect asp ON asp.aspect_key = a.aspect_key
            WHERE a.recommended_action IS NULL OR a.responsible_department IS NULL
            ORDER BY a.alert_key
            """
        )
        cols = ["alert_key", "metric_name", "metric_value", "threshold", "platform_key", "platform_name", "day",
                "aspect_name"]
        alerts = [dict(zip(cols, row)) for row in cur.fetchall()]
    for alert in alerts:
        action, department = build_recommendation(rules, alert, gather_evidence(conn, alert))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dw.fact_alert SET recommended_action = coalesce(recommended_action, %s), "
                "responsible_department = coalesce(responsible_department, %s) WHERE alert_key = %s",
                (action, department, alert["alert_key"]),
            )
    return len(alerts)


def run(conn, detect: bool = True) -> dict:
    """Phát hiện rồi điền khuyến nghị; hàm không commit. Trả về tóm tắt."""
    summary = {"detected": 0, "inserted": 0, "filled": 0}
    if detect:
        found = write_alerts(conn, load_config())
        summary["detected"], summary["inserted"] = found["anomalies"], found["inserted"]
    summary["filled"] = fill_recommendations(conn, load_rules())
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T7: sinh cảnh báo và khuyến nghị vào dw.fact_alert")
    parser.add_argument("--dry-run", action="store_true", help="tính rồi hoàn tác, không ghi")
    parser.add_argument("--skip-detect", action="store_true", help="chỉ điền khuyến nghị cho cảnh báo đã có")
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    with connect(args.env_file) as conn:
        summary = run(conn, detect=not args.skip_detect)
        conn.rollback() if args.dry_run else conn.commit()
    print(f"Bất thường phát hiện: {summary['detected']}, cảnh báo mới: {summary['inserted']}, "
          f"đã điền khuyến nghị: {summary['filled']}{' (dry-run, đã hoàn tác)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
