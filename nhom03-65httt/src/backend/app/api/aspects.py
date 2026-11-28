"""Aspect sentiment API using the local PhoBERT M2 checkpoint when available."""

import sys
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

from app.schemas.aspects import AspectTextIn, AspectsOut
from app.services.aspects_baseline import predict_aspects as predict_keyword_baseline

_ROOT = Path(__file__).resolve().parents[4]
_SRC_ROOT = _ROOT / "src"
_M2_MODEL_DIR = _ROOT / "models" / "m2_absa"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

PHOBERT_MODEL_NAME = "M2_phobert_absa"
BASELINE_MODEL_NAME = "keyword_baseline"
router = APIRouter(prefix="/api/v1/predict", tags=["M2 - cảm xúc theo khía cạnh"])


@lru_cache(maxsize=1)
def _load_phobert_scorer():
    """Load the ignored local model once; clean installs keep the explicit baseline fallback."""
    if not (_M2_MODEL_DIR / "m2_info.json").is_file():
        return None
    try:
        from ml.aspects.m2_phobert_model import Scorer

        return Scorer(_M2_MODEL_DIR)
    except ModuleNotFoundError as exc:
        if exc.name in {"torch", "transformers", "numpy"}:
            return None
        raise


@router.post("/aspects", response_model=AspectsOut, summary="Dự đoán cảm xúc theo khía cạnh")
def predict_aspects_endpoint(payload: AspectTextIn) -> AspectsOut:
    """Use PhoBERT M2 when its checkpoint and runtime are installed; otherwise label the baseline clearly."""
    scorer = _load_phobert_scorer()
    if scorer is not None:
        return AspectsOut(model=PHOBERT_MODEL_NAME, aspects=scorer.predict([payload.text])[0])
    return AspectsOut(model=BASELINE_MODEL_NAME, aspects=predict_keyword_baseline(payload.text))
