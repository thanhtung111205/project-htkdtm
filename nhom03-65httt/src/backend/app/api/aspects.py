"""Aspect sentiment API (keyword baseline until the trained M2 weights are available)."""

from fastapi import APIRouter

from app.schemas.aspects import AspectTextIn, AspectsOut
from app.services.aspects_baseline import predict_aspects

router = APIRouter(prefix="/api/v1/predict", tags=["M2 - cảm xúc theo khía cạnh"])


@router.post("/aspects", response_model=AspectsOut, summary="Dự đoán cảm xúc theo khía cạnh (M2, ABSA)")
def predict_aspects_endpoint(payload: AspectTextIn) -> AspectsOut:
    """Return keyword-baseline predictions for aspects mentioned in the review."""
    return AspectsOut(aspects=predict_aspects(payload.text))
