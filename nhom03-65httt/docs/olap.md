# OLAP trên kho dữ liệu EduVision (Nhóm 03)

Đề cương yêu cầu kho hỗ trợ roll-up, drill-down, slice, dice, pivot. Tài liệu này chỉ dùng cột có thật trong schema `dw`
(xem [erd.md](erd.md), migration 0001 đến 0006). Truy vấn mẫu: [src/bi/olap/olap_queries.sql](../src/bi/olap/olap_queries.sql);
kiểm thử: `python -m pytest src/bi/tests/test_olap.py -q` (cần CSDL có dữ liệu, tự bỏ qua nếu chưa có).

## 1. Phân cấp của từng chiều

| Chiều | Phân cấp (cột có thật) | Ghi chú |
|---|---|---|
| `dim_time` | ngày (`full_date`) → tuần (`week`) → tháng (`month`) → quý (`quarter`) → năm (`year`) | Có thêm `day_of_week`, `is_weekend` (0006). `week` là tuần trong năm nên khi roll-up tuần lên tháng phải gộp qua `full_date`, không gộp theo `week` đơn thuần |
| `dim_hour` | giờ (`hour_key` 0 đến 23) → buổi (`day_part`) | Dùng kèm `dim_time`; `fact_review.hour_key` |
| `dim_platform` | nhóm (`platform_group`: trong_nuoc, quoc_te) → nền tảng (`platform_name`) | Thuộc tính thêm: `category`, `developer` (0006) |
| `dim_aspect` | khía cạnh (`aspect_name`, 5 giá trị) | Phẳng, một mức; chỉ nối qua `fact_review_aspect` |
| `dim_app_version` | nền tảng (`platform_key`) → phiên bản (`version_name`, `release_date`) | Chưa nối được với `fact_review` (fact không có khóa phiên bản), và bảng hiện trống |
| `dim_source` | loại nguồn (`source_type`) → nguồn (`source_name`) | |

## 2. Phép OLAP áp vào chiều nào

| Phép | Chiều | Truy vấn | Ý nghĩa |
|---|---|---|---|
| Roll-up | `dim_time`: tháng → quý → năm | `rollup` (`GROUP BY ROLLUP (year, quarter, month)`) | Gộp dần số đánh giá, sao trung bình lên cấp cao |
| Drill-down | `dim_platform`: nhóm → nền tảng | `drilldown` (`ROLLUP (platform_group, platform_name)`) | Khoan từ nhóm xuống từng nền tảng; mức khía cạnh thêm bằng `fact_review_aspect` JOIN `dim_aspect` khi M2 có dữ liệu |
| Slice | `dim_time` cố định năm 2025 | `slice` | Cắt một lát theo một chiều |
| Dice | `dim_time` (2024 đến 2025), `dim_platform` (trong nước), `dim_source` (kho ứng dụng) | `dice` | Lọc đồng thời nhiều chiều |
| Pivot | `dim_platform` ở hàng, cảm xúc ở cột | `pivot` (`count(*) FILTER`) | Bảng chéo nền tảng x cảm xúc |
| Pivot, drill-down giờ | `dim_hour`: giờ → buổi (`day_part`) | `pivot_hour` | Cảm xúc theo buổi trong ngày (dùng `fact_review.hour_key`) |
| Dice | `dim_platform.category` x `dim_time` (năm) | `dice_category` | So nhóm ngoại ngữ với học tổng hợp theo năm |
| Drill-down | `dim_platform` | `mismatch` | Tỷ lệ cờ lệch pha `fact_review.is_mismatch` theo nền tảng |

## 3. Giới hạn hiện tại

- Cảm xúc ở truy vấn `pivot` quy đổi từ số sao (4 đến 5 tích cực, 3 trung tính, 1 đến 2 tiêu cực), theo [kpi_bhi.md](kpi_bhi.md). Khi nhãn M1 trong `dw.fact_review_sentiment` đầy đủ, có thể thay bằng `sentiment_label` của `dw.v_review_enriched`.
- `is_mismatch` (truy vấn `mismatch`) chỉ có giá trị sau khi M1 chấm nhãn và chạy `dw.refresh_fact_review_sentiment`; hiện mọi dòng rỗng nên `mismatch_rate` rỗng. `category` cần nạp bằng `load_platform_attributes.py`.
- Pivot theo khía cạnh và drill-down xuống khía cạnh chưa chạy được trên dữ liệu thật vì `dw.fact_review_aspect` còn trống (chờ M2). Không có truy vấn mẫu nào giả lập dữ liệu này.
- Roll-up theo phiên bản ứng dụng chưa làm được vì `dw.fact_review` không có khóa phiên bản (đang hỏi Tùng, thuộc việc N5).
- Tệp không chứa dữ liệu thật; chỉ có truy vấn và mô tả.
