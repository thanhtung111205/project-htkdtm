"""Kiểm thử G11 (exp_uit_vsfc.py): đọc UIT-VSFC đúng phần, đúng nhãn (không cần dữ liệu thật)."""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import exp_uit_vsfc as x  # noqa: E402


def test_load_uit_splits_and_drops_bad_rows(tmp_path):
    path = tmp_path / "uit.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["split", "sentence", "sentiment", "topic"])
        writer.writeheader()
        writer.writerows([
            {"split": "train", "sentence": "giảng viên nhiệt tình .", "sentiment": "2", "topic": "0"},
            {"split": "train", "sentence": "", "sentiment": "0", "topic": "0"},          # thiếu câu
            {"split": "test", "sentence": "phòng học nóng .", "sentiment": "0", "topic": "3"},
            {"split": "validation", "sentence": "bình thường .", "sentiment": "1", "topic": "0"},
            {"split": "test", "sentence": "nhãn lạ", "sentiment": "5", "topic": "0"},     # nhãn ngoài 0..2
            {"split": "khac", "sentence": "phần lạ", "sentiment": "1", "topic": "0"},     # phần không biết
        ])
    data = x.load_uit(path)
    assert data["train"] == [{"text": "giảng viên nhiệt tình .", "y": 2}]
    assert data["test"] == [{"text": "phòng học nóng .", "y": 0}]
    assert data["validation"] == [{"text": "bình thường .", "y": 1}]


def test_load_uit_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        x.load_uit(tmp_path / "khong_co.csv")
