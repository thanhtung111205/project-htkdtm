"""Kiểm thử đơn vị cho thí nghiệm E3 (không phụ thuộc CSDL)."""

from __future__ import annotations

import csv
from pathlib import Path
import pytest

from ml.e3.e3_doi_chieu import (
    calculate_spearman,
    compute_rating_diff,
    filter_and_group_trends,
    load_published_app_info,
)


def test_compute_rating_diff():
    """Kiểm tra hàm tính chênh lệch số sao."""
    assert compute_rating_diff(4.5, 4.0) == 0.5
    assert compute_rating_diff(3.64, 4.83) == -1.19
    assert compute_rating_diff(4.7416, 4.7416) == 0.0


def test_load_published_app_info(tmp_path: Path):
    """Kiểm tra đọc app_info.csv lấy snapshot mới nhất."""
    csv_file = tmp_path / "test_app_info.csv"
    data = [
        ["snapshot_date", "product", "store", "score", "ratings", "title"],
        ["2026-11-01", "ELSA Speak", "google_play", "4.2", "100", "ELSA Old"],
        ["2026-11-15", "ELSA Speak", "google_play", "4.5", "150", "ELSA New"],
        ["2026-11-10", "VUIHOC", "app_store_vn", "4.3", "50", "Vuihoc VN"],
    ]
    with csv_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(data)

    info = load_published_app_info(csv_file)
    assert len(info) == 2

    elsa_play = info[("ELSA Speak", "google_play")]
    assert elsa_play["snapshot_date"] == "2026-11-15"
    assert elsa_play["score"] == 4.5
    assert elsa_play["ratings"] == 150

    vuihoc_ios = info[("VUIHOC", "app_store_vn")]
    assert vuihoc_ios["score"] == 4.3


def test_filter_and_group_trends():
    """Kiểm tra lọc bỏ tháng partial và tháng < min_reviews."""
    rows = [
        {"platform_name": "ELSA", "new_review_count": 10, "interest_self_scaled": 50.0, "is_partial": False},
        {"platform_name": "ELSA", "new_review_count": 2, "interest_self_scaled": 60.0, "is_partial": False},  # < 5 reviews
        {"platform_name": "ELSA", "new_review_count": 20, "interest_self_scaled": 70.0, "is_partial": True},   # is_partial
        {"platform_name": "ELSA", "new_review_count": 15, "interest_self_scaled": None, "is_partial": False},  # None interest
        {"platform_name": "VUIHOC", "new_review_count": 30, "interest_self_scaled": 80.0, "is_partial": False},
    ]

    grouped = filter_and_group_trends(rows, min_reviews=5)
    assert "ELSA" in grouped
    assert len(grouped["ELSA"]) == 1
    assert grouped["ELSA"][0] == (10.0, 50.0)

    assert "VUIHOC" in grouped
    assert len(grouped["VUIHOC"]) == 1
    assert grouped["VUIHOC"][0] == (30.0, 80.0)


def test_calculate_spearman_insufficient_samples():
    """Dưới 6 quan sát phải trả về (None, None)."""
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    rho, p_val = calculate_spearman(x, y)
    assert rho is None
    assert p_val is None


def test_calculate_spearman_positive_correlation():
    """Chuỗi đồng biến hoàn hảo phải cho rho = 1.0 và p-value rất nhỏ."""
    x = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
    y = [15.0, 25.0, 35.0, 45.0, 55.0, 65.0, 75.0, 85.0]
    rho, p_val = calculate_spearman(x, y)
    assert rho == 1.0
    assert p_val is not None
    assert p_val < 0.001


def test_calculate_spearman_negative_correlation():
    """Chuỗi nghịch biến hoàn hảo phải cho rho = -1.0."""
    x = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    y = [70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0]
    rho, p_val = calculate_spearman(x, y)
    assert rho == -1.0
    assert p_val is not None
    assert p_val < 0.001
