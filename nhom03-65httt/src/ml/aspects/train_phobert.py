"""Train M2 PhoBERT on LLM aspect labels and evaluate once on human gold.

Run from the nhom03-65httt folder after installing src/ml/sentiment/requirements.txt:

    python src/ml/aspects/train_phobert.py

The 3,775 non-skip training rows are split internally to select the epoch and
per-aspect thresholds. The final model is then retrained on all 3,775 rows.
The held-out human gold workbook set is used only for the final report.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src" / "backend"))
sys.path.insert(0, str(ROOT / "src" / "ml"))

from app.services.aspects_baseline import predict_aspects as predict_baseline  # noqa: E402
from aspects.evaluate_f1 import binary_f1, macro_f1  # noqa: E402
from aspects.m2_phobert_model import (  # noqa: E402
    ASPECT_KEYS,
    ASPECT_NAMES,
    BASE_MODEL,
    MAX_LEN,
    SENTIMENT_LABELS,
    segment,
)

LABEL_DIR = ROOT / "data" / "raw" / "labeling"
ASPECT_HEADERS = {
    "technical": "Kỹ thuật",
    "academic": "Học thuật",
    "customer_service": "CSKH",
    "pricing": "Giá",
}
SENTIMENT_ID = {label: index for index, label in enumerate(SENTIMENT_LABELS)}
VI_SENTIMENT = {"tích cực": "tich_cuc", "trung tính": "trung_tinh", "tiêu cực": "tieu_cuc"}
VI_OVERALL = {**VI_SENTIMENT, "bỏ qua": "bo_qua"}


def say(*parts: Any) -> None:
    print(time.strftime("%H:%M:%S"), *parts, flush=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_training_rows(label_dir: Path = LABEL_DIR) -> tuple[list[dict[str, Any]], dict[str, int]]:
    sample = {row["item_id"]: row for row in read_csv(label_dir / "training_sample_4000.csv")}
    labels = read_csv(label_dir / "llm_labels_train.csv")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    excluded_skip = 0
    for label in labels:
        item_id = label["item_id"].strip()
        if item_id in seen:
            raise ValueError(f"item_id bị lặp trong nhãn huấn luyện: {item_id}")
        seen.add(item_id)
        if label["sentiment"].strip() == "bo_qua":
            excluded_skip += 1
            continue
        if item_id not in sample:
            raise ValueError(f"Không tìm thấy văn bản huấn luyện cho item_id={item_id}")
        presence: list[int] = []
        sentiments: list[int] = []
        for key in ASPECT_KEYS:
            value = label[key].strip()
            if value:
                if value not in SENTIMENT_ID:
                    raise ValueError(f"Nhãn khía cạnh không hợp lệ: {value!r}")
                presence.append(1)
                sentiments.append(SENTIMENT_ID[value])
            else:
                presence.append(0)
                sentiments.append(-100)
        text = sample[item_id]["text"].strip()
        if not text:
            raise ValueError(f"Văn bản huấn luyện rỗng cho item_id={item_id}")
        rows.append({"item_id": item_id, "text": text, "presence": presence, "sentiments": sentiments})
    return rows, {"input_rows": len(labels), "excluded_bo_qua": excluded_skip, "used_rows": len(rows)}


def _normalize_overall(value: Any) -> str | None:
    return VI_OVERALL.get(str(value or "").strip().casefold())


def _normalize_aspect(value: Any) -> str | None:
    return VI_SENTIMENT.get(str(value or "").strip().casefold())


def read_annotators(annotator_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    from openpyxl import load_workbook

    files = sorted(path for path in annotator_dir.glob("BoGanNhan_*.xlsx") if not path.name.startswith("~$"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy workbook gán nhãn trong {annotator_dir}")
    annotators: dict[str, dict[str, dict[str, Any]]] = {}
    for path in files:
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.worksheets[-1]
            iterator = sheet.iter_rows(values_only=True)
            header = [str(value).strip() if value is not None else "" for value in next(iterator)]
            required = ["item_id", "Cảm xúc chung", *ASPECT_HEADERS.values()]
            missing = set(required) - set(header)
            if missing:
                raise ValueError(f"Thiếu cột trong {path.name}: {', '.join(sorted(missing))}")
            indices = {name: header.index(name) for name in required}
            rows: dict[str, dict[str, Any]] = {}
            for values in iterator:
                item_id = str(values[indices["item_id"]] or "").strip()
                if not item_id:
                    continue
                if item_id in rows:
                    raise ValueError(f"item_id bị lặp trong {path.name}: {item_id}")
                rows[item_id] = {
                    "overall": _normalize_overall(values[indices["Cảm xúc chung"]]),
                    "aspects": {
                        key: _normalize_aspect(values[indices[column]])
                        for key, column in ASPECT_HEADERS.items()
                    },
                }
            annotators[path.stem.removeprefix("BoGanNhan_")] = rows
        finally:
            workbook.close()
    return annotators


def build_human_gold(
    annotators: dict[str, dict[str, dict[str, Any]]], label_dir: Path = LABEL_DIR
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    text_by_id = {row["item_id"]: row["text"] for row in read_csv(label_dir / "gold_texts_1200.csv")}
    overall_votes: dict[str, list[str]] = defaultdict(list)
    aspect_votes: dict[str, dict[str, list[str | None]]] = {
        key: defaultdict(list) for key in ASPECT_KEYS
    }
    for labels in annotators.values():
        for item_id, row in labels.items():
            if row["overall"] is not None:
                overall_votes[item_id].append(row["overall"])
            for key in ASPECT_KEYS:
                aspect_votes[key][item_id].append(row["aspects"][key])

    eligible: dict[str, str] = {}
    overall_disagreements = 0
    skipped = 0
    for item_id, votes in overall_votes.items():
        if len(set(votes)) > 1:
            overall_disagreements += 1
        elif votes and votes[0] == "bo_qua":
            skipped += 1
        elif votes:
            eligible[item_id] = votes[0]

    rows: list[dict[str, Any]] = []
    for item_id in sorted(eligible):
        text = text_by_id.get(item_id)
        if not text:
            continue
        presence: dict[str, bool | None] = {}
        sentiments: dict[str, str | None] = {}
        for key in ASPECT_KEYS:
            votes = aspect_votes[key].get(item_id, [])
            present = [value is not None for value in votes]
            if not present or len(set(present)) > 1:
                presence[key] = None
                sentiments[key] = None
            else:
                presence[key] = present[0]
                sentiments[key] = votes[0] if present[0] and len(set(votes)) == 1 else None
        rows.append({"item_id": item_id, "text": text, "presence": presence, "sentiments": sentiments})

    aspect_stats: dict[str, dict[str, int]] = {}
    for key in ASPECT_KEYS:
        scored = [row for row in rows if row["presence"][key] is not None]
        aspect_stats[key] = {
            "n_scored": len(scored),
            "positive": sum(bool(row["presence"][key]) for row in scored),
            "presence_disagreements": sum(row["presence"][key] is None for row in rows),
            "sentiment_consensus": sum(row["sentiments"][key] is not None for row in rows),
        }
    stats = {
        "annotators": {name: len(rows_) for name, rows_ in annotators.items()},
        "human_consensus_items": len(rows),
        "overall_disagreements_dropped": overall_disagreements,
        "bo_qua_dropped": skipped,
        "aspect_gold": aspect_stats,
    }
    return rows, stats


def split_train_validation(rows: list[dict[str, Any]], seed: int, validation_fraction: float):
    indices = list(range(len(rows)))
    random.Random(seed).shuffle(indices)
    validation_size = max(1, round(len(indices) * validation_fraction))
    return indices[validation_size:], indices[:validation_size]


def threshold_f1(probabilities: np.ndarray, targets: np.ndarray) -> tuple[float, float]:
    candidates = [0.05 + step * 0.025 for step in range(37)]
    options = [(binary_f1(targets.astype(bool), probabilities >= threshold), threshold) for threshold in candidates]
    best_f1 = max(score for score, _ in options)
    best_threshold = min((threshold for score, threshold in options if score == best_f1), key=lambda value: abs(value - 0.5))
    return best_f1, best_threshold


def presence_scores(rows, probabilities: np.ndarray, thresholds: dict[str, float], use_gold: bool) -> dict[str, Any]:
    per_aspect: dict[str, dict[str, Any]] = {}
    for index, key in enumerate(ASPECT_KEYS):
        selected = [
            (row, probabilities[row_index, index])
            for row_index, row in enumerate(rows)
            if not use_gold or row["presence"][key] is not None
        ]
        if use_gold:
            actual = [bool(row["presence"][key]) for row, _ in selected]
        else:
            actual = [bool(row["presence"][index]) for row, _ in selected]
        predicted = [float(probability) >= thresholds[key] for _, probability in selected]
        tp = sum(expected and guess for expected, guess in zip(actual, predicted))
        fp = sum(not expected and guess for expected, guess in zip(actual, predicted))
        fn = sum(expected and not guess for expected, guess in zip(actual, predicted))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_aspect[key] = {
            "n": len(actual),
            "positive_gold": sum(actual),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(binary_f1(actual, predicted), 4),
            "threshold": round(float(thresholds[key]), 4),
        }
    return {"per_aspect": per_aspect, "macro_f1": round(macro_f1({key: row["f1"] for key, row in per_aspect.items()}), 4)}


def optimize_thresholds(rows, probabilities: np.ndarray) -> dict[str, float]:
    return {
        key: threshold_f1(probabilities[:, index], np.array([row["presence"][index] for row in rows], dtype=bool))[1]
        for index, key in enumerate(ASPECT_KEYS)
    }


def _tokenize_batch(tokenizer, texts: list[str], device):
    encoded = tokenizer(texts, padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt")
    return {key: value.to(device) for key, value in encoded.items()}


def predict_logits(model, tokenizer, texts: list[str], device, batch_size: int) -> np.ndarray:
    import torch

    model.eval()
    outputs: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            encoded = _tokenize_batch(tokenizer, texts[start : start + batch_size], device)
            outputs.append(model(**encoded).logits.float().cpu().numpy())
    return np.concatenate(outputs, axis=0) if outputs else np.zeros((0, len(ASPECT_KEYS) * 4), dtype=np.float32)


def _training_loss(logits, presence, sentiments, pos_weight, sentiment_weights):
    import torch
    import torch.nn.functional as F

    presence_logits = logits[:, : len(ASPECT_KEYS)]
    sentiment_logits = logits[:, len(ASPECT_KEYS) :].reshape(-1, len(ASPECT_KEYS), len(SENTIMENT_LABELS))
    loss_presence = F.binary_cross_entropy_with_logits(presence_logits, presence.float(), pos_weight=pos_weight)
    sentiment_losses = []
    for index in range(len(ASPECT_KEYS)):
        mask = presence[:, index].bool()
        if mask.any():
            sentiment_losses.append(
                F.cross_entropy(sentiment_logits[mask, index], sentiments[mask, index], weight=sentiment_weights[index])
            )
    loss_sentiment = torch.stack(sentiment_losses).mean() if sentiment_losses else logits.sum() * 0.0
    return loss_presence + 0.5 * loss_sentiment


def fit_model(
    model,
    tokenizer,
    rows,
    indices,
    *,
    epochs,
    batch_size,
    grad_accumulation,
    lr,
    seed,
    device,
    threads,
    validation_rows=None,
):
    import torch
    from transformers import get_linear_schedule_with_warmup
    from phobert_model import length_buckets

    torch.set_num_threads(threads)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    presence_all = torch.tensor([row["presence"] for row in rows], dtype=torch.float32)
    sentiments_all = torch.tensor([row["sentiments"] for row in rows], dtype=torch.long)
    train_presence = presence_all[indices]
    pos_counts = train_presence.sum(0).clamp_min(1.0)
    pos_weight = ((len(indices) - pos_counts) / pos_counts).clamp(min=1.0, max=50.0).to(device)
    sentiment_weights = []
    for index in range(len(ASPECT_KEYS)):
        values = sentiments_all[indices][train_presence[:, index].bool(), index]
        counts = torch.bincount(values, minlength=len(SENTIMENT_LABELS)).float().clamp_min(1.0)
        weights = torch.sqrt(counts.sum() / counts)
        sentiment_weights.append((weights / weights.mean()).to(device))
    sentiment_weights_tensor = torch.stack(sentiment_weights)

    lengths = [len(rows[index]["model_text"].split()) for index in indices]
    first_batches = length_buckets(lengths, batch_size, seed + 1)
    steps_per_epoch = max(1, (len(first_batches) + grad_accumulation - 1) // grad_accumulation)
    total_steps = steps_per_epoch * epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, max(1, int(total_steps * 0.1)), total_steps)
    scaler = torch.cuda.amp.GradScaler(enabled=device.type == "cuda")
    history = []
    best_validation_f1 = -1.0
    best_epoch = 0
    best_thresholds: dict[str, float] = {key: 0.5 for key in ASPECT_KEYS}
    best_validation: dict[str, Any] = {}
    for epoch in range(1, epochs + 1):
        model.train()
        batches = length_buckets(lengths, batch_size, seed + epoch)
        optimizer.zero_grad(set_to_none=True)
        running_loss = 0.0
        seen = 0
        for step, batch in enumerate(batches, start=1):
            global_indices = [indices[local_index] for local_index in batch]
            texts = [rows[index]["model_text"] for index in global_indices]
            encoded = _tokenize_batch(tokenizer, texts, device)
            y_presence = presence_all[global_indices].to(device)
            y_sentiments = sentiments_all[global_indices].to(device)
            with torch.cuda.amp.autocast(enabled=device.type == "cuda"):
                logits = model(**encoded).logits
                loss = _training_loss(logits, y_presence, y_sentiments, pos_weight, sentiment_weights_tensor)
            scaler.scale(loss / grad_accumulation).backward()
            if step % grad_accumulation == 0 or step == len(batches):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            running_loss += float(loss.detach()) * len(global_indices)
            seen += len(global_indices)
            if step % 50 == 0 or step == len(batches):
                say(f"epoch {epoch}/{epochs} batch {step}/{len(batches)} loss {running_loss / max(1, seen):.4f}")
        record = {"epoch": epoch, "train_loss": round(running_loss / max(1, seen), 4)}
        if validation_rows:
            logits = predict_logits(
                model,
                tokenizer,
                [row["model_text"] for row in validation_rows],
                device,
                batch_size=batch_size * 2,
            )
            probabilities = 1.0 / (1.0 + np.exp(-logits[:, : len(ASPECT_KEYS)]))
            thresholds = optimize_thresholds(validation_rows, probabilities)
            scores = presence_scores(validation_rows, probabilities, thresholds, use_gold=False)
            record["validation_macro_f1"] = scores["macro_f1"]
            record["validation_thresholds"] = thresholds
            history.append(record)
            say(f"== epoch {epoch}: validation macro-F1 {scores['macro_f1']} | {thresholds}")
            if scores["macro_f1"] > best_validation_f1:
                best_validation_f1 = scores["macro_f1"]
                best_epoch = epoch
                best_thresholds = thresholds
                best_validation = scores
        else:
            history.append(record)
    if validation_rows:
        return model, history, best_epoch, best_thresholds, best_validation
    return model, history, None, None, None


def new_model():
    from transformers import AutoModelForSequenceClassification

    labels = [f"presence_{key}" for key in ASPECT_KEYS] + [
        f"sentiment_{key}_{label}" for key in ASPECT_KEYS for label in SENTIMENT_LABELS
    ]
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(labels),
        ignore_mismatched_sizes=True,
    )
    model.config.id2label = {index: label for index, label in enumerate(labels)}
    model.config.label2id = {label: index for index, label in enumerate(labels)}
    return model


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Huấn luyện M2 PhoBERT và đo trên tập vàng người gán.")
    parser.add_argument("--label-dir", type=Path, default=LABEL_DIR)
    parser.add_argument("--annotator-dir", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "models" / "m2_absa")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "ml" / "m2_phobert_human_gold.json")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accumulation", type=int, default=4)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--device", default="auto", help="auto, cuda, hoặc cpu")
    args = parser.parse_args(argv)

    import torch
    from transformers import AutoTokenizer

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cuda.matmul.allow_tf32 = True
    device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available() else "cpu" if args.device == "auto" else args.device)

    train_rows, train_stats = load_training_rows(args.label_dir)
    annotator_dir = args.annotator_dir or args.label_dir / "gan_nhan_tung_nguoi"
    gold_rows, gold_stats = build_human_gold(read_annotators(annotator_dir), args.label_dir)
    training_ids = {row["item_id"] for row in train_rows}
    gold_ids = {row["item_id"] for row in gold_rows}
    overlap = training_ids & gold_ids
    if overlap:
        raise ValueError(f"Phát hiện rò item_id giữa train và human gold: {len(overlap)} dòng")
    if not train_rows or not gold_rows:
        raise ValueError("Tập train hoặc tập vàng người gán đang rỗng.")

    say(f"thiết bị {device}; train {len(train_rows)} dòng ({train_stats['excluded_bo_qua']} bo_qua bị loại); vàng người {len(gold_rows)} dòng")
    say(f"F1 aspect gold có số dòng theo khía cạnh: { {key: gold_stats['aspect_gold'][key]['n_scored'] for key in ASPECT_KEYS} }")
    say("đang tách từ văn bản train và gold")
    for row in train_rows + gold_rows:
        row["model_text"] = segment(row["text"])

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    train_indices, validation_indices = split_train_validation(train_rows, args.seed, args.validation_fraction)
    validation = [train_rows[index] for index in validation_indices]
    candidate = new_model()
    candidate, candidate_history, best_epoch, best_thresholds, best_validation = fit_model(
        candidate,
        tokenizer,
        train_rows,
        train_indices,
        epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accumulation=args.grad_accumulation,
        lr=args.lr,
        seed=args.seed,
        device=device,
        threads=args.threads,
        validation_rows=validation,
    )
    if best_epoch == 0:
        raise RuntimeError("Không chọn được epoch tốt nhất trên tập validation.")
    best_macro_f1 = best_validation["macro_f1"]
    del candidate
    if device.type == "cuda":
        torch.cuda.empty_cache()

    say(f"validation macro-F1 {best_macro_f1}; thresholds {best_thresholds}; huấn luyện lại trên đủ {len(train_rows)} dòng trong {best_epoch} epoch")
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    final_model = new_model()
    final_model, final_history, _, _, _ = fit_model(
        final_model,
        tokenizer,
        train_rows,
        list(range(len(train_rows))),
        epochs=best_epoch,
        batch_size=args.batch_size,
        grad_accumulation=args.grad_accumulation,
        lr=args.lr,
        seed=args.seed,
        device=device,
        threads=args.threads,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    final_model.save_pretrained(args.out_dir)
    tokenizer.save_pretrained(args.out_dir)
    model_info = {
        "model": "M2_phobert_absa",
        "base": BASE_MODEL,
        "trained_on": date.today().isoformat(),
        "train_rows": len(train_rows),
        "label_source": "LLM aspect labels; bo_qua excluded",
        "seed": args.seed,
        "best_epoch": best_epoch,
        "validation_macro_f1": best_macro_f1,
        "presence_thresholds": best_thresholds,
        "aspect_keys": list(ASPECT_KEYS),
        "aspect_names": list(ASPECT_NAMES),
        "sentiment_labels": list(SENTIMENT_LABELS),
        "max_len": MAX_LEN,
    }
    (args.out_dir / "m2_info.json").write_text(json.dumps(model_info, ensure_ascii=False, indent=2), encoding="utf-8")

    from aspects.m2_phobert_model import Scorer

    scorer = Scorer(args.out_dir, device=str(device), threads=args.threads)
    # Use the model's batch API; only the agreed human gold rows are evaluated.
    predictions = scorer.predict([row["text"] for row in gold_rows], batch_size=args.batch_size * 2)
    api_name_to_key = {name.casefold(): key for key, name in zip(ASPECT_KEYS, ASPECT_NAMES)}
    model_sets = {
        row["item_id"]: {api_name_to_key[item["aspect_name"].casefold()] for item in pred}
        for row, pred in zip(gold_rows, predictions)
    }
    # Build per-aspect metric rows so disagreements are excluded only for that aspect.
    phobert_presence: dict[str, dict[str, Any]] = {}
    baseline_presence: dict[str, dict[str, Any]] = {}
    for key in ASPECT_KEYS:
        eligible = [row for row in gold_rows if row["presence"][key] is not None]
        y_true = [bool(row["presence"][key]) for row in eligible]
        y_model = [key in model_sets[row["item_id"]] for row in eligible]
        y_base = [
            key in {api_name_to_key[item["aspect_name"].casefold()] for item in predict_baseline(row["text"])}
            for row in eligible
        ]
        phobert_presence[key] = {"n": len(eligible), "positive_gold": sum(y_true), "f1": round(binary_f1(y_true, y_model), 4)}
        baseline_presence[key] = {"n": len(eligible), "positive_gold": sum(y_true), "f1": round(binary_f1(y_true, y_base), 4)}
    phobert_macro = round(macro_f1({key: value["f1"] for key, value in phobert_presence.items()}), 4)
    baseline_macro = round(macro_f1({key: value["f1"] for key, value in baseline_presence.items()}), 4)

    report = {
        "model": model_info,
        "training_data": train_stats,
        "internal_validation": {
            "best_epoch": best_epoch,
            "macro_f1": best_macro_f1,
            "per_aspect": best_validation["per_aspect"],
            "history": candidate_history,
        },
        "human_gold": gold_stats,
        "human_gold_presence": {"phobert": {"macro_f1": phobert_macro, "per_aspect": phobert_presence}, "keyword_baseline": {"macro_f1": baseline_macro, "per_aspect": baseline_presence}},
        "final_train_epochs": final_history,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"PhoBERT human-gold macro-F1 {phobert_macro}; keyword baseline {baseline_macro}")
    for key in ASPECT_KEYS:
        say(f"{key}: PhoBERT F1 {phobert_presence[key]['f1']} (n={phobert_presence[key]['n']}) | baseline {baseline_presence[key]['f1']}")
    say("đã lưu mô hình", args.out_dir)
    say("đã ghi kết quả", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
