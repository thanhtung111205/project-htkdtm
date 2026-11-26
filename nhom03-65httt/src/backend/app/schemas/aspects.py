from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AspectTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000, description="Nội dung đánh giá cần phân tích")

    @field_validator("text")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Văn bản không được để trống.")
        return value


class AspectSentimentOut(BaseModel):
    aspect_name: Literal["Technical", "Academic", "Customer Service", "Pricing", "Other"]
    sentiment_label: Literal["tich_cuc", "trung_tinh", "tieu_cuc"]
    sentiment_score: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)


class AspectsOut(BaseModel):
    aspects: list[AspectSentimentOut]
