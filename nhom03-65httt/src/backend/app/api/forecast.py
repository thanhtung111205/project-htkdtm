"""GET /api/v1/forecast: dự báo M3 (Sentiment Index và tỷ lệ tiêu cực) theo nền tảng, đọc từ dw.fact_forecast (N2).

Trả `periods` tháng gần nhất đã có dòng dự báo, gồm cả tháng kế tiếp (actual rỗng). Nền tảng không tồn tại trả 404,
tham số sai 422, chưa cấu hình hoặc mất kết nối CSDL 503. Nền tảng hợp lệ nhưng chuỗi quá ngắn để dự báo
(ví dụ DUOLINGO, Khan Academy) trả 200 với danh sách rỗng và thông báo.
"""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import get_settings
from app.schemas.common import ErrorOut

router = APIRouter(prefix="/api/v1", tags=["Dự báo"])

TARGET_BY_MODEL = {"M3_sentiment_index": "sentiment_index", "M3_negative_rate": "negative_rate"}


class ForecastValue(BaseModel):
    forecast: float
    ci_lower: float | None
    ci_upper: float | None
    actual: float | None


class ForecastPeriod(BaseModel):
    month: date
    sentiment_index: ForecastValue | None = None
    negative_rate: ForecastValue | None = None


class ForecastOut(BaseModel):
    platform: str
    message: str | None
    periods: list[ForecastPeriod]


@router.get(
    "/forecast",
    response_model=ForecastOut,
    responses={404: {"model": ErrorOut}, 503: {"model": ErrorOut}},
    summary="Dự báo tháng kế tiếp theo nền tảng (M3)",
)
def forecast(
    platform: str = Query(min_length=1, max_length=100, description="Tên nền tảng, ví dụ ELSA Speak"),
    periods: int = Query(default=6, ge=1, le=60, description="Số tháng gần nhất trả về (gồm tháng kế tiếp)"),
) -> ForecastOut:
    url = get_settings().database_url
    if not url:
        raise HTTPException(status_code=503, detail="Chưa cấu hình cơ sở dữ liệu")
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute("SELECT platform_key, platform_name FROM dw.dim_platform WHERE lower(platform_name) = lower(%s)",
                            (platform.strip(),))
                found = cur.fetchone()
                if found is None:
                    raise HTTPException(status_code=404, detail=f"Không có nền tảng {platform!r}")
                key, name = found
                cur.execute(
                    """
                    SELECT t.full_date, m.model_name, f.forecast_value, f.ci_lower, f.ci_upper, f.actual_value
                    FROM dw.fact_forecast f
                    JOIN dw.dim_time t USING (time_key) JOIN dw.dim_model m USING (model_key)
                    WHERE f.platform_key = %s AND m.model_name = ANY(%s)
                      AND t.full_date IN (SELECT t2.full_date FROM dw.fact_forecast f2 JOIN dw.dim_time t2 USING (time_key)
                                          WHERE f2.platform_key = %s GROUP BY t2.full_date ORDER BY t2.full_date DESC LIMIT %s)
                    ORDER BY t.full_date
                    """,
                    (key, list(TARGET_BY_MODEL), key, periods),
                )
                rows = cur.fetchall()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail=f"Không kết nối được cơ sở dữ liệu ({type(exc).__name__})") from exc

    by_month: dict[date, ForecastPeriod] = {}
    for month, model_name, value, lo, hi, actual in rows:
        period = by_month.setdefault(month, ForecastPeriod(month=month))
        setattr(period, TARGET_BY_MODEL[model_name], ForecastValue(
            forecast=float(value), ci_lower=None if lo is None else float(lo),
            ci_upper=None if hi is None else float(hi), actual=None if actual is None else float(actual)))
    message = None
    if not by_month:
        message = "Chưa có dự báo cho nền tảng này (chuỗi tháng đủ 30 đánh giá quá ngắn hoặc chưa chạy M3)"
    elif len(by_month) < periods:
        message = f"Chỉ có {len(by_month)} tháng dự báo, ít hơn {periods} tháng yêu cầu"
    return ForecastOut(platform=name, message=message, periods=list(by_month.values()))
