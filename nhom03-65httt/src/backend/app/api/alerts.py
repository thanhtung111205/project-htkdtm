"""API xem và xử lý cảnh báo (HU3). Quy tắc mức độ: tỷ lệ = metric_value / threshold; threshold <= 0 thì trung_binh; ratio >= 1.5 cao; >= 1.2 trung_binh; còn lại thap."""

from __future__ import annotations

from datetime import date
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.config import get_settings
from app.core.security import require_admin, require_user
from app.schemas.alerts import (
    AlertListOut,
    AlertOut,
    AlertStatusIn,
    AlertSummaryOut,
)
from app.schemas.auth import UserOut

router = APIRouter(prefix="/api/v1/alerts", tags=["Cảnh báo"])

AlertStatus = Literal["moi", "dang_xu_ly", "da_xu_ly"]


def severity(metric_value: float, threshold: float) -> Literal["cao", "trung_binh", "thap"]:
    if threshold <= 0:
        return "trung_binh"
    ratio = metric_value / threshold
    if ratio >= 1.5:
        return "cao"
    if ratio >= 1.2:
        return "trung_binh"
    return "thap"


def database_url() -> str:
    url = get_settings().database_url
    if not url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Chưa cấu hình cơ sở dữ liệu")
    return url


def build_filters(
    platform: str | None,
    alert_status: AlertStatus | None,
    department: str | None,
    start_date: date | None,
    end_date: date | None,
) -> tuple[str, list[object]]:
    conditions: list[str] = ["1=1"]
    params: list[object] = []

    if platform and platform.strip():
        conditions.append("LOWER(p.platform_name) = LOWER(%s)")
        params.append(platform.strip())
    if alert_status is not None:
        conditions.append("a.status = %s")
        params.append(alert_status)
    else:
        conditions.append("a.status <> %s")
        params.append("da_xu_ly")
    if department and department.strip():
        conditions.append("LOWER(a.responsible_department) = LOWER(%s)")
        params.append(department.strip())
    if start_date:
        conditions.append("(a.detected_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("(a.detected_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date <= %s")
        params.append(end_date)

    return " AND ".join(conditions), params


def alert_from_row(row: tuple[object, ...]) -> AlertOut:
    metric_value = float(row[6])
    threshold = float(row[7])
    return AlertOut(
        alert_key=int(row[0]),
        detected_at=row[1],
        detected_date=row[2],
        platform_name=str(row[3]),
        aspect_name=None if row[4] is None else str(row[4]),
        metric_name=str(row[5]),
        metric_value=metric_value,
        threshold=threshold,
        severity=severity(metric_value, threshold),
        status=row[8],
        recommended_action=None if row[9] is None else str(row[9]),
        responsible_department=None if row[10] is None else str(row[10]),
        notified=row[11] is not None,
    )


SELECT_ALERT = """
SELECT a.alert_key,
       a.detected_at,
       (a.detected_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS detected_date,
       p.platform_name,
       asp.aspect_name,
       a.metric_name,
       a.metric_value,
       a.threshold,
       a.status,
       a.recommended_action,
       a.responsible_department,
       a.notified_at
FROM dw.fact_alert a
JOIN dw.dim_platform p ON p.platform_key = a.platform_key
LEFT JOIN dw.dim_aspect asp ON asp.aspect_key = a.aspect_key
"""


@router.get("/summary", response_model=AlertSummaryOut,
            summary="Thống kê cảnh báo chưa xử lý theo nền tảng và mức độ")
def alert_summary(
    platform: str | None = Query(default=None, max_length=100),
    department: str | None = Query(default=None, max_length=200),
    start_date: date | None = None,
    end_date: date | None = None,
    _user: UserOut = Depends(require_user),
) -> AlertSummaryOut:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date phải nhỏ hơn hoặc bằng end_date")

    url = database_url()
    condition, params = build_filters(platform, None, department, start_date, end_date)
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    SELECT_ALERT + " WHERE " + condition,
                    tuple(params),
                )
                rows = cur.fetchall()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503,
                            detail=f"Không truy vấn được cơ sở dữ liệu ({type(exc).__name__})") from exc

    items = [alert_from_row(tuple(row)) for row in rows]
    by_platform: dict[str, int] = {}
    by_severity: dict[str, int] = {"cao": 0, "trung_binh": 0, "thap": 0}
    for item in items:
        by_platform[item.platform_name] = by_platform.get(item.platform_name, 0) + 1
        by_severity[item.severity] = by_severity.get(item.severity, 0) + 1

    return AlertSummaryOut(total=len(items), by_platform=dict(sorted(by_platform.items())),
                           by_severity={key: by_severity[key] for key in ("cao", "trung_binh", "thap")})


@router.get("", response_model=AlertListOut,
            summary="Danh sách cảnh báo có phân trang")
def list_alerts(
    platform: str | None = Query(default=None, max_length=100),
    status: AlertStatus | None = None,
    department: str | None = Query(default=None, max_length=200),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: UserOut = Depends(require_user),
) -> AlertListOut:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date phải nhỏ hơn hoặc bằng end_date")

    url = database_url()
    condition, params = build_filters(platform, status, department, start_date, end_date)
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM dw.fact_alert a JOIN dw.dim_platform p ON p.platform_key = a.platform_key "
                    "LEFT JOIN dw.dim_aspect asp ON asp.aspect_key = a.aspect_key WHERE " + condition,
                    tuple(params),
                )
                total = int(cur.fetchone()[0])

                cur.execute(
                    SELECT_ALERT + " WHERE " + condition
                    + " ORDER BY a.detected_at DESC, a.alert_key DESC LIMIT %s OFFSET %s",
                    tuple(params + [limit, offset]),
                )
                rows = cur.fetchall()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503,
                            detail=f"Không truy vấn được cơ sở dữ liệu ({type(exc).__name__})") from exc

    return AlertListOut(total=total, items=[alert_from_row(tuple(row)) for row in rows])


@router.get("/{alert_key}", response_model=AlertOut,
            summary="Chi tiết một cảnh báo")
def get_alert(
    alert_key: int,
    _user: UserOut = Depends(require_user),
) -> AlertOut:
    url = database_url()
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(SELECT_ALERT + " WHERE a.alert_key = %s", (alert_key,))
                row = cur.fetchone()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503,
                            detail=f"Không truy vấn được cơ sở dữ liệu ({type(exc).__name__})") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    return alert_from_row(tuple(row))


@router.patch("/{alert_key}/status", response_model=AlertOut,
             summary="Cập nhật trạng thái xử lý cảnh báo")
def update_alert_status(
    alert_key: int,
    payload: AlertStatusIn,
    _admin: UserOut = Depends(require_admin),
) -> AlertOut:
    url = database_url()
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE dw.fact_alert SET status = %s WHERE alert_key = %s RETURNING alert_key",
                    (payload.status, alert_key),
                )
                returning = cur.fetchone()
                if returning is None:
                    conn.rollback()
                    raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")

                cur.execute(SELECT_ALERT + " WHERE a.alert_key = %s", (alert_key,))
                row = cur.fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503,
                            detail=f"Không truy vấn được cơ sở dữ liệu ({type(exc).__name__})") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    return alert_from_row(tuple(row))
