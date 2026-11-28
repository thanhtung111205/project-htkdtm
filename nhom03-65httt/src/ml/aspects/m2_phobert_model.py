"""PhoBERT scorer for aspect presence and aspect-specific sentiment (M2)."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[3]
SENTIMENT_DIR = ROOT / "src" / "ml" / "sentiment"
sys.path.insert(0, str(SENTIMENT_DIR))

from phobert_model import BASE_MODEL, MAX_LEN, segment  # noqa: E402

MODEL_DIR = ROOT / "models" / "m2_absa"
ASPECT_KEYS = ("technical", "academic", "customer_service", "pricing")
ASPECT_NAMES = ("Technical", "Academic", "Customer Service", "Pricing")
SENTIMENT_LABELS = ("tich_cuc", "trung_tinh", "tieu_cuc")


class Scorer:
    """Load a locally trained M2 checkpoint and return API-compatible predictions."""

    def __init__(self, model_dir: str | Path = MODEL_DIR, device: str | None = None, threads: int = 4):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        torch.set_num_threads(threads)
        directory = Path(model_dir)
        metadata_path = directory / "m2_info.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy mô hình M2 PhoBERT: {directory}")
        self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.thresholds = self.metadata.get("presence_thresholds", {})
        self.tokenizer = AutoTokenizer.from_pretrained(directory)
        self.model = AutoModelForSequenceClassification.from_pretrained(directory).to(self.device)
        self.model.eval()

    def predict(self, texts: Sequence[str], batch_size: int = 8) -> list[list[dict[str, Any]]]:
        texts = list(texts)
        results: list[list[dict[str, Any]]] = [[] for _ in texts]
        with self.torch.no_grad():
            for start in range(0, len(texts), batch_size):
                batch = [segment(text) for text in texts[start : start + batch_size]]
                encoded = self.tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=MAX_LEN,
                    return_tensors="pt",
                )
                encoded = {key: value.to(self.device) for key, value in encoded.items()}
                logits = self.model(**encoded).logits.float()
                presence = self.torch.sigmoid(logits[:, : len(ASPECT_KEYS)])
                sentiments = self.torch.softmax(
                    logits[:, len(ASPECT_KEYS) :].reshape(-1, len(ASPECT_KEYS), len(SENTIMENT_LABELS)), dim=-1
                )
                for offset in range(len(batch)):
                    for index, (key, name) in enumerate(zip(ASPECT_KEYS, ASPECT_NAMES)):
                        present_probability = float(presence[offset, index])
                        threshold = float(self.thresholds.get(key, 0.5))
                        if present_probability < threshold:
                            continue
                        probabilities = sentiments[offset, index]
                        sentiment_id = int(probabilities.argmax())
                        results[start + offset].append(
                            {
                                "aspect_name": name,
                                "sentiment_label": SENTIMENT_LABELS[sentiment_id],
                                "sentiment_score": round(float(probabilities[0] - probabilities[2]), 3),
                                "confidence": round(present_probability * float(probabilities[sentiment_id]), 3),
                            }
                        )
        return results


@lru_cache(maxsize=1)
def _default_scorer() -> Scorer:
    return Scorer()


def predict_aspects(text: str) -> list[dict[str, Any]]:
    """Function hook for ``score_aspects.py --scorer ml.aspects.m2_phobert_model:predict_aspects``."""
    return _default_scorer().predict([text])[0]
