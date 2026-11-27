"""E1 trên TẬP VÀNG NGƯỜI GÁN: so TF-IDF + LR, PhoBERT và LLM zero-shot với nhãn của nhóm (BoGanNhan_*.xlsx).

Chạy từ thư mục nhom03-65httt (dữ liệu và mô hình nằm ngoài Git):

    python src/ml/sentiment/eval_human_gold.py [--label-dir data/raw/labeling] [--no-phobert]

Cách dựng tập vàng người:
  - Mỗi tệp BoGanNhan_<tên>.xlsx (sheet cuối) có cột item_id và "Cảm xúc chung" (Tích cực, Trung tính, Tiêu cực, Bỏ qua).
  - Dòng một người gán: lấy nhãn đó. Dòng hai người cùng gán: chỉ giữ khi hai người ĐỒNG Ý (bất đồng bị loại, có đếm).
  - Loại "Bỏ qua". Văn bản lấy từ gold_texts_1200.csv. Tập vàng không nằm trong dữ liệu huấn luyện M1.
Đo thêm: Cohen's kappa giữa người với người (dòng gán chung) và giữa người với LLM.
LLM zero-shot là nhãn trong llm_labels_gold.csv (LLM gán không có số sao, theo rubric); LLM trả "bo_qua" ở dòng người
có nhãn thì tính là dự đoán sai. Kết quả: data/ml/e1_human_gold.json.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sentiment_common import LABEL_DIR, LABEL_TO_ID, LABELS, ROOT, _read, metrics  # noqa: E402

VI_TO_LABEL = {"tiêu cực": "tieu_cuc", "trung tính": "trung_tinh", "tích cực": "tich_cuc", "bỏ qua": "bo_qua"}
SKIP = "bo_qua"


def read_annotator(path: Path) -> dict[str, str]:
    """item_id -> nhãn chuẩn (tieu_cuc, trung_tinh, tich_cuc, bo_qua) của một người; ô trống bị bỏ."""
    import openpyxl

    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[-1]
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h else "" for h in next(rows)]
    i_id, i_label = header.index("item_id"), header.index("Cảm xúc chung")
    out = {}
    for row in rows:
        if not row or row[i_id] in (None, ""):
            continue
        value = VI_TO_LABEL.get(str(row[i_label] or "").strip().lower())
        if value:
            out[str(row[i_id]).strip()] = value
    return out


def build_gold(annotators: dict[str, dict[str, str]]) -> tuple[dict[str, str], dict]:
    """Gộp nhãn nhiều người thành tập vàng; trả (item_id -> nhãn, thống kê)."""
    votes: dict[str, list[str]] = defaultdict(list)
    for labels in annotators.values():
        for item, label in labels.items():
            votes[item].append(label)
    gold, disagree = {}, 0
    for item, labels in votes.items():
        if len(set(labels)) > 1:
            disagree += 1
            continue
        if labels[0] != SKIP:
            gold[item] = labels[0]
    stats = {"items_labeled": len(votes), "multi_labeled": sum(len(v) > 1 for v in votes.values()),
             "disagreements_dropped": disagree, "skipped_bo_qua": sum(1 for v in votes.values()
                                                                       if len(set(v)) == 1 and v[0] == SKIP)}
    return gold, stats


def kappa(a: list[str], b: list[str]) -> float:
    from sklearn.metrics import cohen_kappa_score
    return round(float(cohen_kappa_score(a, b)), 4)


def agreement(annotators: dict[str, dict[str, str]], llm: dict[str, str]) -> dict:
    a_all, b_all, pairs = [], [], {}
    for x, y in itertools.combinations(sorted(annotators), 2):
        common = sorted(annotators[x].keys() & annotators[y].keys())
        if common:
            pairs[f"{x}-{y}"] = {"n": len(common), "agree": round(sum(annotators[x][k] == annotators[y][k]
                                                                       for k in common) / len(common), 4)}
            a_all += [annotators[x][k] for k in common]
            b_all += [annotators[y][k] for k in common]
    human = [(lab, llm[item]) for labels in annotators.values() for item, lab in labels.items() if item in llm]
    return {
        "human_human": {"n": len(a_all), "kappa": kappa(a_all, b_all) if a_all else None,
                        "agree": round(sum(p == q for p, q in zip(a_all, b_all)) / len(a_all), 4) if a_all else None,
                        "pairs": pairs},
        "human_llm": {"n": len(human), "kappa": kappa([h for h, _ in human], [m for _, m in human]),
                      "agree": round(sum(h == m for h, m in human) / len(human), 4)},
    }


def to_ids(labels: list[str]) -> list[int]:
    return [LABEL_TO_ID.get(label, -1) for label in labels]  # -1: LLM trả bo_qua, tính là sai


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="E1 trên tập vàng người gán")
    parser.add_argument("--label-dir", type=Path, default=LABEL_DIR)
    parser.add_argument("--annotator-dir", type=Path, default=None,
                        help="thư mục BoGanNhan_*.xlsx (mặc định <label-dir>/gan_nhan_tung_nguoi)")
    parser.add_argument("--tfidf", type=Path, default=ROOT / "models" / "m1_tfidf_lr" / "model.joblib")
    parser.add_argument("--phobert", type=Path, default=ROOT / "models" / "m1_phobert_sentiment")
    parser.add_argument("--no-phobert", action="store_true", help="bỏ PhoBERT (máy không có torch)")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "ml" / "e1_human_gold.json")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ann_dir = args.annotator_dir or args.label_dir / "gan_nhan_tung_nguoi"
    files = sorted(p for p in ann_dir.glob("BoGanNhan_*.xlsx") if not p.name.startswith("~$"))
    if not files:
        print(f"Không thấy tệp BoGanNhan_*.xlsx trong {ann_dir}", file=sys.stderr)
        return 2
    annotators = {p.stem.removeprefix("BoGanNhan_"): read_annotator(p) for p in files}
    texts = {r["item_id"]: r["text"] for r in _read(args.label_dir / "gold_texts_1200.csv")}
    llm = {r["item_id"]: r["sentiment"] for r in _read(args.label_dir / "llm_labels_gold.csv")}

    gold, stats = build_gold(annotators)
    items = sorted(i for i in gold if i in texts)
    y_true = to_ids([gold[i] for i in items])
    batch = [texts[i] for i in items]
    result = {"run_at": datetime.now(timezone.utc).isoformat(), "annotators": {k: len(v) for k, v in annotators.items()},
              "gold": {**stats, "n_eval": len(items), "label_counts": dict(Counter(gold[i] for i in items))},
              "agreement": agreement(annotators, llm), "models": {}}

    result["models"]["LLM_zero_shot"] = metrics(y_true, to_ids([llm.get(i, SKIP) for i in items]))
    result["models"]["LLM_zero_shot"]["llm_bo_qua"] = sum(llm.get(i) == SKIP for i in items)
    if args.tfidf.is_file():
        import joblib
        model = joblib.load(args.tfidf)["model"]
        result["models"]["TFIDF_LR"] = metrics(y_true, [int(p) for p in model.predict(batch)])
    if not args.no_phobert and args.phobert.is_dir():
        from phobert_model import Scorer
        proba = Scorer(args.phobert, args.threads).predict_proba(batch)
        result["models"]["PhoBERT"] = metrics(y_true, [int(row.argmax()) for row in proba])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ag = result["agreement"]
    print(f"Người gán: {result['annotators']}")
    print(f"Tập vàng người: {len(items)} dòng {result['gold']['label_counts']} | gán chung {stats['multi_labeled']}, "
          f"bất đồng bị loại {stats['disagreements_dropped']}, bỏ qua {stats['skipped_bo_qua']}")
    print(f"Kappa người-người {ag['human_human']['kappa']} (đồng ý {ag['human_human']['agree']}, {ag['human_human']['n']} dòng); "
          f"người-LLM {ag['human_llm']['kappa']} (đồng ý {ag['human_llm']['agree']})")
    for name, m in result["models"].items():
        print(f"  {name:14} macro-F1 {m['macro_f1']}  accuracy {m['accuracy']}  F1 {m['f1_per_class']}")
    print("Đã lưu", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
