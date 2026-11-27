"""G11 (đề cương mục 4.3 và 8.1): E1 CÓ và KHÔNG dùng dữ liệu bổ trợ UIT-VSFC, để kiểm tra khả năng tổng quát hóa.

Chạy từ thư mục nhom03-65httt (dữ liệu nằm ngoài Git):

    python src/ml/sentiment/exp_uit_vsfc.py [--uit data/raw/public/uit_vsfc.csv]

Ba cấu hình, cùng mô hình TF-IDF + Logistic Regression (train_baseline.build_pipeline), C chọn trên validation của nhóm:
  A. chỉ dữ liệu của nhóm (80% của 4.000 đánh giá, nhãn LLM)          = M1 nền hiện tại
  B. dữ liệu của nhóm + phần train của UIT-VSFC (11.426 câu)           = có dữ liệu bổ trợ
  B2. dữ liệu của nhóm + mẫu UIT-VSFC CÙNG cỡ với dữ liệu nhóm (hạt 42)  = bổ trợ nhưng không để UIT lấn át
  C. chỉ UIT-VSFC train                                                 = mốc: dữ liệu ngoài miền dùng một mình
Đo trên: test của nhóm (10%, nhãn LLM), tập vàng NGƯỜI GÁN (BoGanNhan, nếu có), tập vàng LLM, và test UIT-VSFC
(3.166 câu phản hồi sinh viên, khác miền với đánh giá ứng dụng).
Nhãn UIT-VSFC: 0 tiêu cực, 1 trung tính, 2 tích cực, trùng thứ tự LABELS. UIT-VSFC đã tách từ sẵn bằng khoảng trắng
và viết thường; TF-IDF cũng viết thường nên không cần chuẩn hóa thêm.
PhoBERT không chạy lại ở đây (khoảng 3 giờ trên CPU với dữ liệu gấp 4 lần); kết luận chỉ áp dụng cho mô hình nền.
Kết quả: data/ml/e1_uit_vsfc.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sentiment_common import LABEL_DIR, LABEL_TO_ID, ROOT, SEED, _read, load_gold, load_train, metrics, split_stratified  # noqa: E402
from train_baseline import build_pipeline  # noqa: E402

C_GRID = (0.5, 1.0, 2.0, 4.0, 8.0)


def load_uit(path: Path) -> dict[str, list[dict]]:
    """UIT-VSFC theo phần (train, validation, test): text, y. Bỏ dòng thiếu câu hoặc nhãn ngoài 0..2."""
    if not path.is_file():
        raise FileNotFoundError(f"Không thấy UIT-VSFC: {path}")
    csv.field_size_limit(10**9)
    out: dict[str, list[dict]] = {"train": [], "validation": [], "test": []}
    for row in _read(path):
        text, label = (row.get("sentence") or "").strip(), (row.get("sentiment") or "").strip()
        if text and label in ("0", "1", "2") and row.get("split") in out:
            out[row["split"]].append({"text": text, "y": int(label)})
    return out


def human_gold(label_dir: Path) -> list[dict]:
    """Tập vàng người gán như eval_human_gold.py (đồng ý giữa người gán, bỏ bo_qua). Rỗng nếu chưa có tệp."""
    from eval_human_gold import build_gold, read_annotator

    ann_dir = label_dir / "gan_nhan_tung_nguoi"
    files = sorted(p for p in ann_dir.glob("BoGanNhan_*.xlsx") if not p.name.startswith("~$"))
    if not files:
        return []
    gold, _ = build_gold({p.stem: read_annotator(p) for p in files})
    texts = {r["item_id"]: r["text"] for r in _read(label_dir / "gold_texts_1200.csv")}
    return [{"text": texts[i], "y": LABEL_TO_ID[gold[i]]} for i in sorted(gold) if i in texts]


def fit(train: list[dict], c: float):
    model = build_pipeline(c)
    model.fit([r["text"] for r in train], [r["y"] for r in train])
    return model


def evaluate(model, rows: list[dict]) -> dict | None:
    if not rows:
        return None
    return metrics([r["y"] for r in rows], [int(p) for p in model.predict([r["text"] for r in rows])])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="G11: E1 có và không dùng UIT-VSFC (TF-IDF + LR)")
    parser.add_argument("--uit", type=Path, default=ROOT / "data" / "raw" / "public" / "uit_vsfc.csv")
    parser.add_argument("--label-dir", type=Path, default=LABEL_DIR)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "ml" / "e1_uit_vsfc.json")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    train, val, test = split_stratified(load_train(args.label_dir))
    uit = load_uit(args.uit)
    eval_sets = {"test_nhom": test, "vang_nguoi": human_gold(args.label_dir),
                 "vang_llm": load_gold(args.label_dir), "test_uit_vsfc": uit["test"]}
    uit_same_size = random.Random(SEED).sample(uit["train"], min(len(train), len(uit["train"])))
    configs = {"A_chi_nhom": train, "B_nhom_cong_uit": train + uit["train"],
               "B2_nhom_cong_uit_cung_co": train + uit_same_size, "C_chi_uit": uit["train"]}
    print("Cỡ tập:", {k: len(v) for k, v in {**configs, **eval_sets}.items()})

    result = {"run_at": datetime.now(timezone.utc).isoformat(), "model": "tfidf_lr",
              "sizes": {k: len(v) for k, v in {**configs, **eval_sets}.items()}, "configs": {}}
    for name, rows in configs.items():
        best_c, best_f1 = None, -1.0
        for c in C_GRID:  # chọn C trên validation của NHÓM: mục tiêu là đánh giá ứng dụng
            f1 = evaluate(fit(rows, c), val)["macro_f1"]
            if f1 > best_f1:
                best_c, best_f1 = c, f1
        model = fit(rows, best_c)
        result["configs"][name] = {"C": best_c, "validation_macro_f1": best_f1,
                                   **{k: evaluate(model, v) for k, v in eval_sets.items()}}
        line = "  ".join(f"{k} {m['macro_f1']} (TT {m['f1_per_class']['trung_tinh']})"
                         for k, m in result["configs"][name].items() if isinstance(m, dict))
        print(f"{name:26} C={best_c:<4} {line}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Đã lưu", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
