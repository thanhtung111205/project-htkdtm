"""Aspect sentiment API; this endpoint currently serves the keyword baseline."""

from fastapi import APIRouter

from app.schemas.aspects import AspectTextIn, AspectsOut
from app.services.aspects_baseline import predict_aspects

MODEL_NAME = "keyword_baseline"
router = APIRouter(prefix="/api/v1/predict", tags=["M2 baseline - cảm xúc theo khía cạnh"])


@router.post("/aspects", response_model=AspectsOut, summary="Dự đoán cảm xúc theo khía cạnh (keyword baseline)")
def predict_aspects_endpoint(payload: AspectTextIn) -> AspectsOut:
    """Return keyword-baseline predictions for aspects mentioned in the review."""
    return AspectsOut(model=MODEL_NAME, aspects=predict_aspects(payload.text))
