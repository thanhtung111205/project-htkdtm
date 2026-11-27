-- EduVision BI - Nhóm 03: năm truy vấn OLAP mẫu trên schema dw (đề cương: roll-up, drill-down, slice, dice, pivot).
-- Chỉ dùng cột có thật (xem docs/olap.md). Sentiment tạm quy đổi từ số sao như docs/kpi_bhi.md:
-- 4-5 sao tích cực, 3 sao trung tính, 1-2 sao tiêu cực (đến khi nhãn M1 đầy đủ).
-- Mỗi truy vấn tách bằng dòng "-- @query <tên>" để kiểm thử tách và chạy riêng.

-- @query rollup
-- PHÉP: roll-up. CHIỀU: dim_time (tháng -> quý -> năm). Ý NGHĨA: số đánh giá mới và sao trung bình, gộp dần từ tháng lên quý lên năm
-- (dòng có quarter/month rỗng là tổng cấp trên; dòng cuối là tổng toàn bộ).
SELECT t.year, t.quarter, t.month,
       count(*)                       AS review_count,
       round(avg(f.rating), 2)        AS avg_rating
FROM dw.fact_review f
JOIN dw.dim_time t ON t.time_key = f.time_key
GROUP BY ROLLUP (t.year, t.quarter, t.month)
ORDER BY t.year NULLS LAST, t.quarter NULLS LAST, t.month NULLS LAST;

-- @query drilldown
-- PHÉP: drill-down. CHIỀU: dim_platform (nhóm trong nước/quốc tế -> nền tảng). Ý NGHĨA: từ số đánh giá của cả nhóm xuống từng nền tảng.
-- (Mức khía cạnh dùng dw.fact_review_aspect, xem docs/olap.md; bảng này chỉ có dữ liệu sau khi M2 chạy.)
SELECT p.platform_group, p.platform_name,
       count(*)                AS review_count,
       round(avg(f.rating), 2) AS avg_rating,
       GROUPING(p.platform_name) AS is_group_subtotal
FROM dw.fact_review f
JOIN dw.dim_platform p ON p.platform_key = f.platform_key
GROUP BY ROLLUP (p.platform_group, p.platform_name)
ORDER BY p.platform_group NULLS LAST, p.platform_name NULLS FIRST;

-- @query slice
-- PHÉP: slice (cố định một chiều). CHIỀU: dim_time = năm 2025. Ý NGHĨA: đánh giá của năm 2025 theo nền tảng.
SELECT p.platform_name, count(*) AS review_count, round(avg(f.rating), 2) AS avg_rating
FROM dw.fact_review f
JOIN dw.dim_time t     ON t.time_key = f.time_key
JOIN dw.dim_platform p ON p.platform_key = f.platform_key
WHERE t.year = 2025
GROUP BY p.platform_name
ORDER BY review_count DESC;

-- @query dice
-- PHÉP: dice (lọc nhiều chiều). CHIỀU: dim_time (2024-2025), dim_platform (nhóm trong nước), dim_source (kho ứng dụng).
-- Ý NGHĨA: đánh giá trên kho ứng dụng của nền tảng trong nước trong hai năm gần đây, theo quý.
SELECT t.year, t.quarter, count(*) AS review_count, round(avg(f.rating), 2) AS avg_rating
FROM dw.fact_review f
JOIN dw.dim_time t     ON t.time_key = f.time_key
JOIN dw.dim_platform p ON p.platform_key = f.platform_key
JOIN dw.dim_source s   ON s.source_key = f.source_key
WHERE t.year BETWEEN 2024 AND 2025
  AND p.platform_group = 'trong_nuoc'
  AND s.source_type = 'kho_ung_dung'
GROUP BY t.year, t.quarter
ORDER BY t.year, t.quarter;

-- @query pivot
-- PHÉP: pivot. CHIỀU: dim_platform ở hàng, cảm xúc (quy đổi từ số sao) ở cột. Ý NGHĨA: bảng chéo nền tảng x cảm xúc.
SELECT p.platform_name,
       count(*) FILTER (WHERE f.rating BETWEEN 4 AND 5) AS tich_cuc,
       count(*) FILTER (WHERE f.rating = 3)             AS trung_tinh,
       count(*) FILTER (WHERE f.rating BETWEEN 1 AND 2) AS tieu_cuc,
       count(*)                                         AS tong
FROM dw.fact_review f
JOIN dw.dim_platform p ON p.platform_key = f.platform_key
WHERE f.rating IS NOT NULL
GROUP BY p.platform_name
ORDER BY tong DESC;

-- ---------------------------------------------------------------- mở rộng: cột bổ sung của migration 0006
-- @query pivot_hour
-- PHÉP: pivot (và drill-down giờ -> buổi). CHIỀU: dim_hour (buổi trong ngày) ở hàng, cảm xúc quy đổi từ số sao ở cột.
-- Ý NGHĨA: đánh giá tiêu cực tập trung vào buổi nào trong ngày. hour_key theo giờ Việt Nam.
SELECT h.day_part,
       count(*) FILTER (WHERE f.rating BETWEEN 4 AND 5) AS tich_cuc,
       count(*) FILTER (WHERE f.rating = 3)             AS trung_tinh,
       count(*) FILTER (WHERE f.rating BETWEEN 1 AND 2) AS tieu_cuc,
       count(*)                                         AS tong
FROM dw.fact_review f
JOIN dw.dim_hour h ON h.hour_key = f.hour_key
WHERE f.rating IS NOT NULL
GROUP BY h.day_part
ORDER BY min(h.hour_key);

-- @query dice_category
-- PHÉP: dice. CHIỀU: dim_platform.category (ngoại ngữ so với học tổng hợp) x dim_time (năm). Ý NGHĨA: so hai nhóm nội dung theo năm.
SELECT t.year, p.category, count(*) AS review_count, round(avg(f.rating), 2) AS avg_rating
FROM dw.fact_review f
JOIN dw.dim_time t     ON t.time_key = f.time_key
JOIN dw.dim_platform p ON p.platform_key = f.platform_key
WHERE p.category IS NOT NULL AND t.year >= 2022
GROUP BY t.year, p.category
ORDER BY t.year, p.category;

-- @query mismatch
-- PHÉP: drill-down theo nền tảng. CHỈ SỐ: cờ lệch pha is_mismatch (sao cao mà nhãn tiêu cực, hoặc sao thấp mà nhãn tích cực).
-- is_mismatch chỉ có giá trị sau khi M1 chấm nhãn (dw.refresh_fact_review_sentiment); trước đó mismatch_rate rỗng.
SELECT p.platform_name,
       count(f.is_mismatch)                         AS labeled_reviews,
       count(*) FILTER (WHERE f.is_mismatch)        AS mismatch_count,
       round(count(*) FILTER (WHERE f.is_mismatch)::numeric / NULLIF(count(f.is_mismatch), 0), 4) AS mismatch_rate
FROM dw.fact_review f
JOIN dw.dim_platform p ON p.platform_key = f.platform_key
GROUP BY p.platform_name
ORDER BY p.platform_name;
