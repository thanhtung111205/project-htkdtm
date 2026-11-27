"""POST /api/v1/predict/sentiment: M1 cảm xúc 3 lớp (T2), chạy thật.

Dùng PhoBERT đã tinh chỉnh nếu máy chủ có mô hình và thư viện torch, không thì mô hình nền TF-IDF (trường `model` cho biết).
Văn bản rỗng hoặc dài quá 5.000 ký tự trả 422; chưa có mô hình nào trả 503 kèm lý do.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.common import ErrorOut, TextIn
from app.services import sentiment

router = APIRouter(prefix="/api/v1", tags=["AI"])

LABEL_VI = {"tieu_cuc": "Tiêu cực", "trung_tinh": "Trung tính", "tich_cuc": "Tích cực"}


class SentimentOut(BaseModel):
    label: str  # tieu_cuc | trung_tinh | tich_cuc
    label_vi: str
    confidence: float
    scores: dict[str, float]
    model: str  # M1_phobert, hoặc M1_tfidf_lr khi máy chủ không có PhoBERT


@router.post(
    "/predict/sentiment",
    response_model=SentimentOut,
    responses={503: {"model": ErrorOut}},
    summary="Dự đoán cảm xúc 3 lớp (M1, PhoBERT)",
)
def predict_sentiment(payload: TextIn) -> SentimentOut:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Văn bản chỉ có khoảng trắng")
    try:
        model_name, results = sentiment.predict([text])
    except sentiment.ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Mô hình cảm xúc M1 chưa sẵn sàng: {exc}") from exc
    res = results[0]
    return SentimentOut(label=res["label"], label_vi=LABEL_VI[res["label"]], confidence=res["confidence"],
                        scores=res["scores"], model=model_name)
