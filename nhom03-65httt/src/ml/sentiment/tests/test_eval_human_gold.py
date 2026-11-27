"""Kiểm thử cách dựng tập vàng người cho E1 (không cần tệp dữ liệu thật hay mô hình)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import eval_human_gold as e  # noqa: E402


def test_build_gold_keeps_agreement_drops_disagreement_and_skip():
    annotators = {
        "A": {"1": "tich_cuc", "2": "tieu_cuc", "3": "bo_qua", "4": "trung_tinh"},
        "B": {"2": "tieu_cuc", "4": "tich_cuc", "5": "tieu_cuc"},
    }
    gold, stats = e.build_gold(annotators)
    assert gold == {"1": "tich_cuc", "2": "tieu_cuc", "5": "tieu_cuc"}
    assert stats == {"items_labeled": 5, "multi_labeled": 2, "disagreements_dropped": 1, "skipped_bo_qua": 1}


def test_llm_skip_counts_as_wrong_prediction():
    assert e.to_ids(["tieu_cuc", "trung_tinh", "tich_cuc", "bo_qua"]) == [0, 1, 2, -1]
    m = e.metrics([0, 1, 2], e.to_ids(["tieu_cuc", "bo_qua", "tich_cuc"]))
    assert m["accuracy"] == round(2 / 3, 4)


def test_agreement_counts_pairs():
    annotators = {"A": {"1": "tich_cuc", "2": "tieu_cuc"}, "B": {"1": "tich_cuc", "2": "trung_tinh"}}
    ag = e.agreement(annotators, {"1": "tich_cuc", "2": "tieu_cuc"})
    assert ag["human_human"]["n"] == 2 and ag["human_human"]["agree"] == 0.5
    assert ag["human_llm"]["n"] == 4 and ag["human_llm"]["agree"] == 0.75
