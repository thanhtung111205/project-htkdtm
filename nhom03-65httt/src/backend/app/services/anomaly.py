"""Phát hiện bất thường tỷ lệ tiêu cực theo kỳ hai tuần (N4). Quy tắc thống kê, không huấn luyện.

Đường cơ sở = trung bình 8 kỳ trước cộng 2 độ lệch chuẩn (mẫu). Kỳ hai tuần neo vào thứ Hai 2011-01-03.
Hàm thuần (detect, period_start) không cần CSDL nên kiểm thử được bằng chuỗi mẫu.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import psycopg

ANCHOR = date(2011, 1, 3)  # thứ Hai; kỳ hai tuần đếm từ đây
DEFAULTS = {"window": 8, "k": 2.0, "min_delta": 0.05, "min_reviews": 10, "metric_name": "negative_rate_2w",
            "recent_periods_to_alert": 4}


def load_config(path: Path | None = None) -> dict:
    """Đọc config/anomaly.yml nếu tìm thấy (ảnh Docker của API không chứa tệp này nên có giá trị mặc định)."""
    cfg = dict(DEFAULTS)
    if path is None:
        for parent in Path(__file__).resolve().parents:
            if (parent / "config" / "anomaly.yml").is_file():
                path = parent / "config" / "anomaly.yml"
                break
    if path is not None and path.is_file():
        import yaml

        cfg.update(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    return cfg


def period_start(d: date) -> date:
    return ANCHOR + timedelta(days=14 * ((d - ANCHOR).days // 14))


@dataclass
class PeriodResult:
    period_start: date
    period_end: date
    reviews: int
    value: float
    baseline_mean: float | None = None
    baseline_std: float | None = None
    threshold: float | None = None
    is_anomaly: bool = False
    events: list[str] = field(default_factory=list)


def detect(series: list[tuple[date, int, int]], window: int = 8, k: float = 2.0, min_delta: float = 0.05,
           min_reviews: int = 10) -> list[PeriodResult]:
    """series: (ngày đầu kỳ, số đánh giá có sao, số đánh giá tiêu cực). Trả kết quả từng kỳ, theo thời gian.

    Kỳ ít hơn min_reviews đánh giá bị bỏ khỏi chuỗi. Kỳ chưa đủ `window` kỳ trước thì không tính (is_anomaly False).
    """
    kept = sorted((s for s in series if s[1] >= min_reviews), key=lambda s: s[0])
    results: list[PeriodResult] = []
    for i, (start, total, neg) in enumerate(kept):
        res = PeriodResult(start, start + timedelta(days=13), total, neg / total)
        if i >= window:
            prev = [kept[j][2] / kept[j][1] for j in range(i - window, i)]
            mean, std = statistics.fmean(prev), statistics.stdev(prev)
            res.baseline_mean, res.baseline_std, res.threshold = mean, std, mean + k * std
            res.is_anomaly = res.value > res.threshold and (res.value - mean) >= min_delta
        results.append(res)
    return results


def fetch_series(conn: psycopg.Connection, platform: str | None = None) -> dict[str, list[tuple[date, int, int]]]:
    """Gom dw.fact_review theo (nền tảng, kỳ hai tuần): (ngày đầu kỳ, số đánh giá có sao, số có sao 1 đến 2)."""
    sql = """
        SELECT p.platform_name, t.full_date, count(*), count(*) FILTER (WHERE f.rating <= 2)
        FROM dw.fact_review f
        JOIN dw.dim_time t ON t.time_key = f.time_key
        JOIN dw.dim_platform p ON p.platform_key = f.platform_key
        WHERE f.rating IS NOT NULL AND (%s::text IS NULL OR p.platform_name = %s)
        GROUP BY 1, 2
    """
    buckets: dict[tuple[str, date], list[int]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, (platform, platform))
        for name, day, total, neg in cur.fetchall():
            b = buckets.setdefault((name, period_start(day)), [0, 0])
            b[0] += total
            b[1] += neg
    out: dict[str, list[tuple[date, int, int]]] = {}
    for (name, start), (total, neg) in buckets.items():
        out.setdefault(name, []).append((start, total, neg))
    return out


def find_platform(conn: psycopg.Connection, name: str) -> str | None:
    """Tên nền tảng chuẩn trong dw.dim_platform (không phân biệt hoa thường), hoặc None nếu không có."""
    with conn.cursor() as cur:
        cur.execute("SELECT platform_name FROM dw.dim_platform WHERE lower(platform_name) = lower(%s)", (name.strip(),))
        row = cur.fetchone()
    return row[0] if row else None


def attach_events(conn: psycopg.Connection, platform: str, results: list[PeriodResult]) -> None:
    """Gắn nhãn sự kiện đã biết (dw.dim_event) trùng thời gian của kỳ; dim_event có thể còn trống."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.event_type, e.description, e.start_date, coalesce(e.end_date, e.start_date)
            FROM dw.dim_event e LEFT JOIN dw.dim_platform p ON p.platform_key = e.platform_key
            WHERE e.platform_key IS NULL OR p.platform_name = %s
            """,
            (platform,),
        )
        events = cur.fetchall()
    for res in results:
        res.events = [f"{etype}: {desc or ''}".strip() for etype, desc, s, e in events
                      if s <= res.period_end and e >= res.period_start]
