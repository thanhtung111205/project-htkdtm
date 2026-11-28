"""Điểm cuối AI còn là KHUNG, trả 501 cho tới khi mô hình/LLM được tích hợp (M1 cảm xúc đã chạy thật, xem sentiment.py).

Hợp đồng (đường dẫn, dữ liệu vào) được chốt sớm để website và n8n có thể gọi thử.
"""

from fastapi import APIRouter, HTTPException

from app.schemas.common import ErrorOut, TextIn

router = APIRouter(prefix="/api/v1", tags=["AI (khung, chưa tích hợp)"])

_NOT_READY = {501: {"model": ErrorOut, "description": "Chưa tích hợp"}}


def _not_implemented(what: str) -> HTTPException:
    return HTTPException(status_code=501, detail=f"{what} chưa được tích hợp")


@router.post("/predict/aspects", responses=_NOT_READY, summary="Dự đoán cảm xúc theo khía cạnh (M2, ABSA)")
def predict_aspects(payload: TextIn) -> None:
    raise _not_implemented("Mô hình khía cạnh M2")
