"""GET /api/v1/anomaly: phát hiện bất thường tỷ lệ tiêu cực theo kỳ hai tuần cho một nền tảng (N4).

Nền tảng lạ trả 404, tham số sai trả 422, chưa cấu hình hoặc mất kết nối CSDL trả 503.
Dưới 8 kỳ dữ liệu thì không tính: trả 200 với status "khong_du_ky" và thông báo rõ.
"""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import get_settings
from app.schemas.common import ErrorOut
from app.services.anomaly import attach_events, detect, fetch_series, find_platform, load_config

router = APIRouter(prefix="/api/v1", tags=["Bất thường"])


class AnomalyPeriod(BaseModel):
    period_start: date
    period_end: date
    reviews: int
    negative_rate: float
    baseline_mean: float | None
    baseline_std: float | None
    threshold: float | None
    is_anomaly: bool
    events: list[str]


class AnomalyOut(BaseModel):
    platform: str
    metric: str
    status: str  # ok | khong_du_ky
    message: str | None
    periods: list[AnomalyPeriod]


@router.get(
    "/anomaly",
    response_model=AnomalyOut,
    responses={404: {"model": ErrorOut}, 503: {"model": ErrorOut}},
    summary="Kỳ bất thường của tỷ lệ tiêu cực theo nền tảng (kỳ hai tuần)",
)
def anomaly(
    platform: str = Query(min_length=1, max_length=100, description="Tên nền tảng, ví dụ ELSA Speak"),
    periods: int = Query(default=12, ge=1, le=200, description="Số kỳ gần nhất trả về"),
) -> AnomalyOut:
    url = get_settings().database_url
    if not url:
        raise HTTPException(status_code=503, detail="Chưa cấu hình cơ sở dữ liệu")
    cfg = load_config()
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.read_only = True
            name = find_platform(conn, platform)
            if name is None:
                raise HTTPException(status_code=404, detail=f"Không có nền tảng {platform!r}")
            results = detect(fetch_series(conn, name).get(name, []), cfg["window"], cfg["k"], cfg["min_delta"],
                             cfg["min_reviews"])
            attach_events(conn, name, results)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail=f"Không kết nối được cơ sở dữ liệu ({type(exc).__name__})") from exc

    message = None
    status = "ok"
    if len(results) <= cfg["window"]:
        status = "khong_du_ky"
        message = (f"Chỉ có {len(results)} kỳ hai tuần đủ dữ liệu; cần ít nhất {cfg['window'] + 1} kỳ "
                   f"({cfg['window']} kỳ cơ sở và 1 kỳ xét) nên chưa tính bất thường")
    return AnomalyOut(
        platform=name, metric=cfg["metric_name"], status=status, message=message,
        periods=[AnomalyPeriod(period_start=r.period_start, period_end=r.period_end, reviews=r.reviews,
                               negative_rate=round(r.value, 4),
                               baseline_mean=None if r.baseline_mean is None else round(r.baseline_mean, 4),
                               baseline_std=None if r.baseline_std is None else round(r.baseline_std, 4),
                               threshold=None if r.threshold is None else round(r.threshold, 4),
                               is_anomaly=r.is_anomaly, events=r.events) for r in results[-periods:]],
    )
