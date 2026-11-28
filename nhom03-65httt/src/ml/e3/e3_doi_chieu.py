"""Thí nghiệm E3 (mục 8.3 đề cương): Đối chiếu dữ liệu thu thập.

Bao gồm:
  (a) Mẫu thu thập so với số sao công bố trên cửa hàng ứng dụng (Google Play, App Store).
  (b) Số đánh giá mới hàng tháng so với mức quan tâm tìm kiếm Google Trends.

Chạy:
    python src/ml/e3/e3_doi_chieu.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any

# Đảm bảo import common từ src/etl
_CURRENT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _CURRENT_DIR.parents[1]
_ETL_DIR = _SRC_DIR / "etl"
if str(_ETL_DIR) not in sys.path:
    sys.path.insert(0, str(_ETL_DIR))

from common import connect, project_root  # noqa: E402


def compute_rating_diff(sample_avg: float, published_score: float) -> float:
    """Tính chênh lệch giữa số sao TB mẫu và số sao công bố trên cửa hàng."""
    return round(float(sample_avg) - float(published_score), 4)


def load_published_app_info(csv_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Đọc app_info.csv lấy ảnh chụp mới nhất cho mỗi cặp (product, store)."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy tệp thông tin ứng dụng: {csv_path}")

    latest_info: dict[tuple[str, str], dict[str, Any]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            product = (row.get("product") or "").strip()
            store = (row.get("store") or "").strip()
            if not product or not store:
                continue

            snapshot_date = (row.get("snapshot_date") or "").strip()
            key = (product, store)

            if key not in latest_info or (snapshot_date and snapshot_date > latest_info[key]["snapshot_date"]):
                score_str = (row.get("score") or "").strip()
                ratings_str = (row.get("ratings") or "").strip()
                latest_info[key] = {
                    "score": float(score_str) if score_str else None,
                    "ratings": int(float(ratings_str)) if ratings_str else None,
                    "snapshot_date": snapshot_date,
                    "title": (row.get("title") or "").strip(),
                }
    return latest_info


def query_sample_ratings(conn) -> list[dict[str, Any]]:
    """Lấy số sao TB và phân bố 1-5 sao từ dw.fact_review theo nền tảng và cửa hàng."""
    sql = """
        SELECT p.platform_name, s.source_name, count(*) as sample_size,
               round(avg(f.rating)::numeric, 4) as avg_rating,
               count(*) FILTER (WHERE f.rating = 1) as r1,
               count(*) FILTER (WHERE f.rating = 2) as r2,
               count(*) FILTER (WHERE f.rating = 3) as r3,
               count(*) FILTER (WHERE f.rating = 4) as r4,
               count(*) FILTER (WHERE f.rating = 5) as r5
        FROM dw.fact_review f
        JOIN dw.dim_platform p ON f.platform_key = p.platform_key
        JOIN dw.dim_source s ON f.source_key = s.source_key
        WHERE s.source_type = 'kho_ung_dung'
        GROUP BY p.platform_name, s.source_name
        ORDER BY p.platform_name, s.source_name
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def run_part_a(conn, app_info_path: Path) -> list[dict[str, Any]]:
    """Thực hiện đối chiếu phần (a): Mẫu thu thập vs Số sao công bố."""
    sample_data = query_sample_ratings(conn)
    published_info = load_published_app_info(app_info_path)

    results = []
    for item in sample_data:
        p_name = item["platform_name"]
        s_name = item["source_name"]
        pub = published_info.get((p_name, s_name), {})

        score_pub = pub.get("score")
        ratings_pub = pub.get("ratings")
        sample_avg = float(item["avg_rating"])
        diff = compute_rating_diff(sample_avg, score_pub) if score_pub is not None else None

        results.append({
            "platform": p_name,
            "store": s_name,
            "sample_avg": sample_avg,
            "published_score": score_pub,
            "diff": diff,
            "sample_size": item["sample_size"],
            "published_ratings": ratings_pub,
            "star_distribution": {
                "1_star": item["r1"],
                "2_star": item["r2"],
                "3_star": item["r3"],
                "4_star": item["r4"],
                "5_star": item["r5"],
            },
        })
    return results


def query_trends_and_reviews(conn) -> list[dict[str, Any]]:
    """Lấy số đánh giá mới và mức quan tâm Google Trends theo tháng."""
    sql = """
        SELECT v.platform_name, v.month_start, v.new_review_count, t.interest_self_scaled, t.is_partial
        FROM dw.v_platform_month v
        JOIN clean.trends_monthly t
          ON v.platform_name = t.platform_name AND v.month_start = t.month
        WHERE t.interest_self_scaled IS NOT NULL
        ORDER BY v.platform_name, v.month_start
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def filter_and_group_trends(
    rows: list[dict[str, Any]], min_reviews: int = 5
) -> dict[str, list[tuple[float, float]]]:
    """Lọc bỏ tháng partial và tháng < min_reviews, gom nhóm theo platform."""
    grouped: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        if r.get("is_partial"):
            continue
        cnt = r.get("new_review_count") or 0
        if cnt < min_reviews:
            continue
        interest = r.get("interest_self_scaled")
        if interest is None:
            continue

        p = r["platform_name"]
        if p not in grouped:
            grouped[p] = []
        grouped[p].append((float(cnt), float(interest)))
    return grouped


def calculate_spearman(x: list[float], y: list[float]) -> tuple[float | None, float | None]:
    """Tính hệ số tương quan thứ hạng Spearman và p-value.
    
    Yêu cầu tối thiểu 6 quan sát; nếu ít hơn trả về (None, None).
    """
    n = len(x)
    if n < 6 or len(y) != n:
        return None, None

    try:
        from scipy.stats import spearmanr
        res = spearmanr(x, y)
        return round(float(res.statistic), 4), float(res.pvalue)
    except ImportError:
        # Dự phòng tính Spearman chuẩn khi môi trường không có scipy
        def _rank(vals: list[float]) -> list[float]:
            sorted_indices = sorted(range(len(vals)), key=lambda i: vals[i])
            ranks = [0.0] * len(vals)
            i = 0
            while i < len(vals):
                j = i
                while j < len(vals) - 1 and vals[sorted_indices[j]] == vals[sorted_indices[j + 1]]:
                    j += 1
                avg_rank = (i + j + 2) / 2.0  # 1-indexed
                for k in range(i, j + 1):
                    ranks[sorted_indices[k]] = avg_rank
                i = j + 1
            return ranks

        rx = _rank(x)
        ry = _rank(y)
        mean_rx = sum(rx) / n
        mean_ry = sum(ry) / n
        cov = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
        std_x = math.sqrt(sum((rx[i] - mean_rx) ** 2 for i in range(n)))
        std_y = math.sqrt(sum((ry[i] - mean_ry) ** 2 for i in range(n)))
        if std_x == 0 or std_y == 0:
            return 0.0, 1.0
        rho = cov / (std_x * std_y)
        # T-statistic cho p-value
        if abs(rho) >= 1.0:
            p_val = 0.0
        else:
            t_stat = rho * math.sqrt((n - 2) / (1.0 - rho ** 2))
            # Xấp xỉ normal 2-tailed cho mẫu n >= 6
            p_val = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t_stat) / math.sqrt(2))))
        return round(rho, 4), p_val


def run_part_b(conn) -> list[dict[str, Any]]:
    """Thực hiện đối chiếu phần (b): Số đánh giá vs Google Trends."""
    raw_rows = query_trends_and_reviews(conn)
    grouped = filter_and_group_trends(raw_rows, min_reviews=5)

    results = []
    # Lấy danh sách tất cả các platform có trong raw_rows
    all_platforms = sorted({r["platform_name"] for r in raw_rows})
    for p in all_platforms:
        pairs = grouped.get(p, [])
        n_months = len(pairs)
        if n_months < 6:
            results.append({
                "platform": p,
                "months_count": n_months,
                "spearman_rho": None,
                "p_value": None,
                "status": "không đủ dữ liệu",
            })
        else:
            x = [pt[0] for pt in pairs]
            y = [pt[1] for pt in pairs]
            rho, p_val = calculate_spearman(x, y)
            if len(x) >= 7:
                dx = [x[i] - x[i - 1] for i in range(1, len(x))]
                dy = [y[i] - y[i - 1] for i in range(1, len(y))]
                rho_diff, p_val_diff = calculate_spearman(dx, dy)
            else:
                rho_diff, p_val_diff = None, None

            results.append({
                "platform": p,
                "months_count": n_months,
                "spearman_rho": rho,
                "p_value": p_val,
                "spearman_rho_diff": rho_diff,
                "p_value_diff": p_val_diff,
                "status": "đủ dữ liệu",
            })
    return results


def format_table_a(data: list[dict[str, Any]]) -> str:
    lines = [
        "| Nền tảng | Cửa hàng | Sao TB mẫu | Sao công bố | Chênh lệch | Cỡ mẫu | Số lượt công bố |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for d in data:
        diff_str = f"{d['diff']:+.2f}" if d["diff"] is not None else "N/A"
        pub_score_str = f"{d['published_score']:.2f}" if d["published_score"] is not None else "N/A"
        pub_n_str = f"{d['published_ratings']:,}" if d["published_ratings"] is not None else "N/A"
        lines.append(
            f"| {d['platform']} | {d['store']} | {d['sample_avg']:.2f} | {pub_score_str} | {diff_str} | {d['sample_size']} | {pub_n_str} |"
        )
    return "\n".join(lines)


def format_table_b(data: list[dict[str, Any]]) -> str:
    lines = [
        "| Nền tảng | Số tháng | Spearman rho (Mức độ) | p-value | Spearman rho (Sai phân) | p-value (Sai phân) | Trạng thái |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for d in data:
        if d["spearman_rho"] is not None:
            diff_rho_str = f"{d['spearman_rho_diff']:+.4f}" if d.get("spearman_rho_diff") is not None else "N/A"
            diff_p_str = f"{d['p_value_diff']:.4e}" if d.get("p_value_diff") is not None else "N/A"
            lines.append(
                f"| {d['platform']} | {d['months_count']} | {d['spearman_rho']:+.4f} | {d['p_value']:.4e} | {diff_rho_str} | {diff_p_str} | {d['status']} |"
            )
        else:
            lines.append(
                f"| {d['platform']} | {d['months_count']} | N/A | N/A | N/A | N/A | {d['status']} |"
            )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Thí nghiệm E3: Đối chiếu dữ liệu thu thập")
    parser.add_argument(
        "--app-info",
        type=Path,
        default=project_root() / "data" / "raw" / "context" / "app_info.csv",
        help="Đường dẫn tệp app_info.csv",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=project_root() / "data" / "ml" / "e3_doi_chieu.json",
        help="Đường dẫn lưu kết quả JSON (ngoài Git)",
    )
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    with connect() as conn:
        print("Đang chạy thí nghiệm E3 (a): Mẫu thu thập vs Sao công bố...")
        res_a = run_part_a(conn, args.app_info)
        table_a = format_table_a(res_a)
        print("\n" + table_a + "\n")

        print("Đang chạy thí nghiệm E3 (b): Đánh giá mới vs Google Trends...")
        res_b = run_part_b(conn)
        table_b = format_table_b(res_b)
        print("\n" + table_b + "\n")

        output_payload = {
            "part_a": res_a,
            "part_b": res_b,
        }

        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with args.output_json.open("w", encoding="utf-8") as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=2)
        print(f"Đã lưu kết quả chi tiết vào: {args.output_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
