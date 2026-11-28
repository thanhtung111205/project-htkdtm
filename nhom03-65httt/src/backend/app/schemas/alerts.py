from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


AlertStatus = Literal["moi", "dang_xu_ly", "da_xu_ly"]
Severity = Literal["cao", "trung_binh", "thap"]


class AlertStatusIn(BaseModel):
    status: AlertStatus


class AlertOut(BaseModel):
    alert_key: int
    detected_at: datetime
    detected_date: date
    platform_name: str
    aspect_name: str | None = None
    metric_name: str
    metric_value: float
    threshold: float
    severity: Severity
    status: AlertStatus
    recommended_action: str | None = None
    responsible_department: str | None = None
    notified: bool


class AlertListOut(BaseModel):
    total: int = Field(ge=0)
    items: list[AlertOut]


class AlertSummaryOut(BaseModel):
    total: int = Field(ge=0)
    by_platform: dict[str, int]
    by_severity: dict[Severity, int]
