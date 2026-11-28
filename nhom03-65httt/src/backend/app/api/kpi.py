"""API KPI và Brand Health Index (BHI) đọc dữ liệu tổng hợp trong schema dw."""

from __future__ import annotations

from datetime import date
import os
from pathlib import Path
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import get_settings


router = APIRouter(prefix="/api/v1", tags=["KPI và BHI"])


def _read_env_file() -> dict[str, str]:
    """Tìm .env ngược từ thư mục mã nguồn khi chạy API cục bộ, không ghi bí mật vào mã."""
    result: dict[str, str] = {}
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.is_file():
            for raw in candidate.read_text(encoding="utf-8-sig").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip().strip('"').strip("'")
            break
    return result


def resolve_database_url() -> str:
    """Ưu tiên DATABASE_URL; sau đó POSTGRES_*; cuối cùng đọc .env ngược từ dự án."""
    configured = get_settings().database_url.strip()
    if configured:
        return configured

    file_env = _read_env_file()

    def value(name: str, default: str = "") -> str:
        return os.getenv(name, file_env.get(name, default)).strip()

    database_url = value("DATABASE_URL")
    if database_url:
        return database_url

    password = value("POSTGRES_PASSWORD")
    if not password:
        return ""
    user = value("POSTGRES_USER", "eduvision")
    host = value("POSTGRES_HOST", "127.0.0.1")
    port = value("POSTGRES_PORT", "5432")
    database = value("POSTGRES_DB", "eduvision")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


class KpiFilters(BaseModel):
    platform_name: str | None = None
    platform_group: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class KpiPeriod(BaseModel):
    month: date
    platform_name: str
    platform_group: str
    new_review_count: int
    positive_rate: float | None = None
    negative_rate: float | None = None
    avg_rating: float | None = None
    sentiment_index: float | None = None
    bhi: float | None = None
    review_share_in_group: float | None = None


class KpiOut(BaseModel):
    status: str = "ok"
    message: str | None = None
    filters: KpiFilters
    data: list[KpiPeriod]


class BhiPoint(BaseModel):
    month: date
    platform_name: str
    platform_group: str
    review_count: int
    sentiment_index: float | None = None
    avg_rating: float | None = None
    bhi: float | None = None
    flags: list[str]


class BhiOut(BaseModel):
    status: str
    message: str | None = None
    filters: KpiFilters
    data: list[BhiPoint]


class AspectOut(BaseModel):
    status: str
    message: str | None = None
    filters: KpiFilters
    data: list[dict[str, Any]]


def _validate_dates(start_date: date | None, end_date: date | None) -> None:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date phải nhỏ hơn hoặc bằng end_date")


def _build_filters(platform_name: str | None, platform_group: str | None,
                   start_date: date | None, end_date: date | None) -> tuple[str, list[Any]]:
    conditions = ["1=1"]
    params: list[Any] = []
    if platform_name and platform_name.strip():
        conditions.append("LOWER(platform_name) = LOWER(%s)")
        params.append(platform_name.strip())
    if platform_group and platform_group.strip():
        conditions.append("LOWER(platform_group) = LOWER(%s)")
        params.append(platform_group.strip())
    if start_date:
        conditions.append("month_start >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("month_start <= %s")
        params.append(end_date)
    return " AND ".join(conditions), params


def fetch_platform_month(database_url: str, platform_name: str | None,
                         platform_group: str | None, start_date: date | None,
                         end_date: date | None) -> list[tuple[Any, ...]]:
    condition, params = _build_filters(platform_name, platform_group, start_date, end_date)
    with psycopg.connect(database_url, connect_timeout=3) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT month_start, platform_name, platform_group,
                       new_review_count, positive_rate, negative_rate,
                       avg_rating, sentiment_index, bhi, review_share_in_group
                FROM dw.v_platform_month
                WHERE {condition}
                ORDER BY month_start DESC, platform_name
                """,
                tuple(params),
            )
            return cur.fetchall()


def _as_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _as_int(value: Any) -> int:
    return 0 if value is None else int(value)


@router.get("/kpi", response_model=KpiOut, summary="KPI chính theo nền tảng và tháng")
def kpi(
    platform_name: str | None = Query(default=None, max_length=100),
    platform: str | None = Query(default=None, max_length=100, description="Tên miền tương thích cũ với platform_name"),
    platform_group: str | None = Query(default=None, max_length=100),
    start_date: date | None = None,
    end_date: date | None = None,
) -> KpiOut:
    platform_name = platform_name or platform
    _validate_dates(start_date, end_date)
    database_url = resolve_database_url()
    if not database_url:
        raise HTTPException(status_code=503, detail="Chưa cấu hình cơ sở dữ liệu")

    try:
        rows = fetch_platform_month(database_url, platform_name, platform_group, start_date, end_date)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail=f"Không kết nối được cơ sở dữ liệu ({type(exc).__name__})") from exc

    data = [
        KpiPeriod(
            month=row[0], platform_name=row[1], platform_group=row[2],
            new_review_count=_as_int(row[3]), positive_rate=_as_float(row[4]),
            negative_rate=_as_float(row[5]), avg_rating=_as_float(row[6]),
            sentiment_index=_as_float(row[7]), bhi=_as_float(row[8]),
            review_share_in_group=_as_float(row[9]),
        )
        for row in rows
    ]
    message = None if data else "Không có dữ liệu KPI cho bộ lọc đã chọn"
    return KpiOut(
        status="ok" if data else "khong_co_du_lieu",
        message=message,
        filters=KpiFilters(platform_name=platform_name, platform_group=platform_group,
                           start_date=start_date, end_date=end_date),
        data=data,
    )


@router.get("/bhi", response_model=BhiOut, summary="Brand Health Index theo nền tảng và tháng")
def bhi(
    platform_name: str | None = Query(default=None, max_length=100),
    platform: str | None = Query(default=None, max_length=100, description="Tên miền tương thích cũ với platform_name"),
    platform_group: str | None = Query(default=None, max_length=100),
    start_date: date | None = None,
    end_date: date | None = None,
) -> BhiOut:
    platform_name = platform_name or platform
    _validate_dates(start_date, end_date)
    database_url = resolve_database_url()
    if not database_url:
        raise HTTPException(status_code=503, detail="Chưa cấu hình cơ sở dữ liệu")

    try:
        rows = fetch_platform_month(database_url, platform_name, platform_group, start_date, end_date)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail=f"Không kết nối được cơ sở dữ liệu ({type(exc).__name__})") from exc

    data: list[BhiPoint] = []
    for row in rows:
        review_count = _as_int(row[3])
        sentiment_index = _as_float(row[7])
        avg_rating = _as_float(row[6])
        bhi_value = _as_float(row[8])

        # Fallback theo đúng công thức BI nếu fact đã có chỉ số SI và rating nhưng còn thiếu cột BHI.
        if bhi_value is None and sentiment_index is not None and avg_rating is not None:
            sentiment_score = 50.0 + sentiment_index / 2.0
            rating_score = (avg_rating - 1.0) / 4.0 * 100.0
            bhi_value = max(0.0, min(100.0, round(0.6 * sentiment_score + 0.4 * rating_score, 2)))

        flags = ["du_lieu_it"] if review_count < 30 else []
        data.append(BhiPoint(
            month=row[0], platform_name=row[1], platform_group=row[2],
            review_count=review_count, sentiment_index=sentiment_index,
            avg_rating=avg_rating, bhi=bhi_value, flags=flags,
        ))

    message = None if data else "Không có dữ liệu BHI cho bộ lọc đã chọn"
    return BhiOut(status="ok" if data else "khong_co_du_lieu", message=message,
                  filters=KpiFilters(platform_name=platform_name, platform_group=platform_group,
                                     start_date=start_date, end_date=end_date), data=data)


@router.get("/kpi/aspects", response_model=AspectOut, summary="Dữ liệu cảm xúc theo khía cạnh ABSA")
def kpi_aspects(
    platform_name: str | None = Query(default=None, max_length=100),
    platform_group: str | None = Query(default=None, max_length=100),
    start_date: date | None = None,
    end_date: date | None = None,
) -> AspectOut:
    _validate_dates(start_date, end_date)
    database_url = resolve_database_url()
    if not database_url:
        raise HTTPException(status_code=503, detail="Chưa cấu hình cơ sở dữ liệu")

    filters = KpiFilters(platform_name=platform_name, platform_group=platform_group,
                         start_date=start_date, end_date=end_date)
    try:
        with psycopg.connect(database_url, connect_timeout=3) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('dw.fact_review_aspect') IS NOT NULL")
                exists = bool(cur.fetchone()[0])
                if not exists:
                    return AspectOut(status="khong_co_du_lieu", message="Chưa có bảng dw.fact_review_aspect",
                                     filters=filters, data=[])

                conditions = ["1=1"]
                params: list[Any] = []
                if platform_name and platform_name.strip():
                    conditions.append("LOWER(p.platform_name) = LOWER(%s)"); params.append(platform_name.strip())
                if platform_group and platform_group.strip():
                    conditions.append("LOWER(p.platform_group) = LOWER(%s)"); params.append(platform_group.strip())
                if start_date:
                    conditions.append("dt.full_date >= %s"); params.append(start_date)
                if end_date:
                    conditions.append("dt.full_date <= %s"); params.append(end_date)

                cur.execute(
                    f"""
                    SELECT p.platform_name, p.platform_group, a.aspect_name,
                           a2.sentiment_label, count(*)
                    FROM dw.fact_review_aspect a2
                    JOIN dw.dim_platform p ON p.platform_key = a2.platform_key
                    JOIN dw.dim_aspect a ON a.aspect_key = a2.aspect_key
                    JOIN dw.dim_time dt ON dt.time_key = a2.time_key
                    WHERE {' AND '.join(conditions)}
                    GROUP BY p.platform_name, p.platform_group, a.aspect_name, a2.sentiment_label
                    ORDER BY p.platform_name, a.aspect_name, a2.sentiment_label
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail=f"Không kết nối được cơ sở dữ liệu ({type(exc).__name__})") from exc

    data = [
        {"platform_name": r[0], "platform_group": r[1], "aspect_name": r[2],
         "sentiment_label": r[3], "count": int(r[4])}
        for r in rows
    ]
    message = None
    if not data:
        message = "Chưa có dữ liệu khía cạnh; dw.fact_review_aspect hiện có 0 dòng do mô hình M2 chưa chạy"
    return AspectOut(status="ok" if data else "khong_co_du_lieu", message=message,
                     filters=filters, data=data)
