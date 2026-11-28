"""POST /api/v1/chat: chatbot hỏi đáp trên số liệu (T6, tầng 1: truy vấn có tham số, xem app/services/chatbot.py).

Cần đăng nhập (Viewer hoặc Admin). Kết nối CSDL ở chế độ chỉ đọc, mỗi câu lệnh tối đa 5 giây.
Chưa cấu hình hoặc mất kết nối CSDL thì trả 503; câu hỏi rỗng hoặc chỉ có khoảng trắng trả 422.
"""

from __future__ import annotations

from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import require_user
from app.schemas.auth import UserOut
from app.schemas.common import ChatIn, ErrorOut
from app.services.chatbot import Responder, Store

router = APIRouter(prefix="/api/v1", tags=["Chatbot"])


class ChatOut(BaseModel):
    answer: str = Field(description="Câu trả lời tiếng Việt, có thể chứa **đậm** kiểu Markdown")
    intent: str = Field(description="Ý định nhận ra: overview, compare, compare_platforms, compare_group, trend, "
                                    "forecast, alert, event, news, explain, unknown")
    mode: str = Field(default="truy_van_tham_so", description="truy_van_tham_so (tầng 1); tầng 2 Text-to-SQL làm sau")
    platforms: list[str] = []
    period: str | None = None
    data: list[dict[str, Any]] = Field(default_factory=list, description="Số liệu dùng để trả lời (để vẽ bảng hoặc biểu đồ)")
    suggestions: list[str] = []


@router.post(
    "/chat",
    response_model=ChatOut,
    responses={401: {"model": ErrorOut}, 422: {"model": ErrorOut}, 503: {"model": ErrorOut}},
    summary="Chatbot hỏi đáp trên số liệu (tầng 1: truy vấn có tham số)",
)
def chat(payload: ChatIn, _user: UserOut = Depends(require_user)) -> ChatOut:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Câu hỏi không được để trống")
    url = get_settings().database_url
    if not url:
        raise HTTPException(status_code=503, detail="Chưa cấu hình cơ sở dữ liệu")
    try:
        with psycopg.connect(url, connect_timeout=3, options="-c statement_timeout=5000") as conn:
            conn.read_only = True
            result = Responder(Store(conn)).answer(question)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Không truy vấn được cơ sở dữ liệu") from exc
    return ChatOut(answer=result.answer, intent=result.intent, platforms=result.platforms, period=result.period,
                   data=result.data, suggestions=result.suggestions)
