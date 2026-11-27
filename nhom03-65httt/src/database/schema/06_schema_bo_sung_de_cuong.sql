-- EduVision BI - Nhóm 03: bổ sung cột còn thiếu so với đề cương (mục 7.1, 7.2, 10) và tiêu chí chấm (b).
-- Chạy sau 05_schema_alert_notify.sql. Chạy lại nhiều lần không lỗi, không sinh trùng. Không dùng ký tự phần trăm trong tệp này
-- (trình điều khiển hiểu nhầm là tham số).
--
-- G1  dw.dim_time: thứ trong tuần và cờ cuối tuần (cột sinh tự động, nên mọi mã nạp ngày cũ và mới đều đúng, không phải sửa);
--     dw.dim_hour: chiều giờ trong ngày (0 đến 23, buổi trong ngày); dw.fact_review.hour_key trỏ tới chiều này.
--     Vì dim_time chia theo NGÀY (khóa yyyymmdd), giờ được tách thành chiều riêng đúng chuẩn Kimball thay vì đổi khóa ngày.
-- G2  dw.dim_platform: nhà phát triển và nhóm (học tổng hợp, ngoại ngữ); giá trị nạp bằng load_platform_attributes.py.
-- G3  dw.fact_review: độ dài, nhãn và điểm cảm xúc M1, cờ lệch pha (sao 4 đến 5 mà tiêu cực, hoặc sao 1 đến 2 mà tích cực).
--     Nhãn gốc vẫn ở dw.fact_review_sentiment; các cột này là bản sao để truy vấn OLAP; hàm dw.refresh_fact_review_sentiment đồng bộ.
-- G4  dw.fact_alert: đề xuất hành động và bộ phận phụ trách; dw.v_alert_open hiển thị thêm hai cột này.

-- ---------------------------------------------------------------- G1: thời gian
ALTER TABLE dw.dim_time
    ADD COLUMN IF NOT EXISTS day_of_week smallint GENERATED ALWAYS AS (extract(isodow FROM full_date)::smallint) STORED;
ALTER TABLE dw.dim_time
    ADD COLUMN IF NOT EXISTS is_weekend boolean GENERATED ALWAYS AS (extract(isodow FROM full_date) >= 6) STORED;
COMMENT ON COLUMN dw.dim_time.day_of_week IS 'Thứ trong tuần theo ISO: 1 là thứ Hai đến 7 là Chủ nhật (cột sinh tự động từ full_date)';
COMMENT ON COLUMN dw.dim_time.is_weekend IS 'Cuối tuần: thứ Bảy hoặc Chủ nhật (cột sinh tự động từ full_date)';

CREATE TABLE IF NOT EXISTS dw.dim_hour (
    hour_key    smallint PRIMARY KEY CHECK (hour_key BETWEEN 0 AND 23),
    hour_label  text NOT NULL,
    day_part    text NOT NULL CHECK (day_part IN ('dem', 'sang', 'chieu', 'toi'))
);
COMMENT ON TABLE dw.dim_hour IS 'Chiều giờ trong ngày theo giờ Việt Nam (0 đến 23) và buổi: dem 0-5, sang 6-11, chieu 12-17, toi 18-23. Kết hợp dim_time (ngày) cho phân tích theo giờ';
INSERT INTO dw.dim_hour (hour_key, hour_label, day_part)
SELECT h, lpad(h::text, 2, '0') || ':00',
       CASE WHEN h < 6 THEN 'dem' WHEN h < 12 THEN 'sang' WHEN h < 18 THEN 'chieu' ELSE 'toi' END
FROM generate_series(0, 23) AS g(h)
ON CONFLICT (hour_key) DO NOTHING;

ALTER TABLE dw.fact_review ADD COLUMN IF NOT EXISTS hour_key smallint REFERENCES dw.dim_hour (hour_key);
COMMENT ON COLUMN dw.fact_review.hour_key IS 'Giờ đăng đánh giá theo giờ Việt Nam (0 đến 23); rỗng nếu nguồn không có giờ';
UPDATE dw.fact_review f
   SET hour_key = extract(hour FROM r.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::smallint
  FROM clean.review_text c
  JOIN raw.review_raw r ON r.source = c.source AND r.review_id = c.review_id
 WHERE c.review_key = f.review_key AND f.hour_key IS NULL AND r.created_at IS NOT NULL;

-- ---------------------------------------------------------------- G2: nền tảng
ALTER TABLE dw.dim_platform ADD COLUMN IF NOT EXISTS developer text;
ALTER TABLE dw.dim_platform ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE dw.dim_platform DROP CONSTRAINT IF EXISTS ck_platform_category;
ALTER TABLE dw.dim_platform ADD CONSTRAINT ck_platform_category CHECK (category IS NULL OR category IN ('hoc_tong_hop', 'ngoai_ngu'));
COMMENT ON COLUMN dw.dim_platform.developer IS 'Nhà phát triển theo cửa hàng ứng dụng (lấy từ app_info.csv)';
COMMENT ON COLUMN dw.dim_platform.category IS 'Nhóm nội dung: hoc_tong_hop (học tổng hợp) hoặc ngoai_ngu (ngoại ngữ); do nhóm phân loại';

-- ---------------------------------------------------------------- G3: đánh giá
ALTER TABLE dw.fact_review ADD COLUMN IF NOT EXISTS review_length integer;
ALTER TABLE dw.fact_review ADD COLUMN IF NOT EXISTS sentiment_label text;
ALTER TABLE dw.fact_review ADD COLUMN IF NOT EXISTS sentiment_score numeric(4,3);
ALTER TABLE dw.fact_review ADD COLUMN IF NOT EXISTS is_mismatch boolean;
ALTER TABLE dw.fact_review DROP CONSTRAINT IF EXISTS ck_review_sentiment_label;
ALTER TABLE dw.fact_review ADD CONSTRAINT ck_review_sentiment_label
    CHECK (sentiment_label IS NULL OR sentiment_label IN ('tich_cuc', 'trung_tinh', 'tieu_cuc'));
ALTER TABLE dw.fact_review DROP CONSTRAINT IF EXISTS ck_review_sentiment_score;
ALTER TABLE dw.fact_review ADD CONSTRAINT ck_review_sentiment_score
    CHECK (sentiment_score IS NULL OR sentiment_score BETWEEN -1 AND 1);
COMMENT ON COLUMN dw.fact_review.review_length IS 'Số ký tự của văn bản đã làm sạch';
COMMENT ON COLUMN dw.fact_review.sentiment_label IS 'Bản sao nhãn cảm xúc M1 từ dw.fact_review_sentiment (đồng bộ bằng dw.refresh_fact_review_sentiment)';
COMMENT ON COLUMN dw.fact_review.sentiment_score IS 'Bản sao điểm cảm xúc M1 (P tích cực trừ P tiêu cực, thang -1 đến 1)';
COMMENT ON COLUMN dw.fact_review.is_mismatch IS 'Cờ lệch pha: sao 4 đến 5 mà nhãn tiêu cực, hoặc sao 1 đến 2 mà nhãn tích cực; rỗng nếu thiếu sao hoặc nhãn';

UPDATE dw.fact_review f
   SET review_length = length(c.text)
  FROM clean.review_text c
 WHERE c.review_key = f.review_key AND f.review_length IS NULL;

CREATE OR REPLACE FUNCTION dw.refresh_fact_review_sentiment(p_keys bigint[] DEFAULT NULL)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    changed bigint;
BEGIN
    UPDATE dw.fact_review f
       SET sentiment_label = s.sentiment_label,
           sentiment_score = s.sentiment_score,
           is_mismatch = CASE
               WHEN f.rating IS NULL THEN NULL
               WHEN (f.rating >= 4 AND s.sentiment_label = 'tieu_cuc')
                 OR (f.rating <= 2 AND s.sentiment_label = 'tich_cuc') THEN true
               ELSE false
           END
      FROM dw.fact_review_sentiment s
     WHERE s.review_key = f.review_key
       AND (p_keys IS NULL OR f.review_key = ANY (p_keys))
       AND (f.sentiment_label IS DISTINCT FROM s.sentiment_label
            OR f.sentiment_score IS DISTINCT FROM s.sentiment_score
            OR (f.is_mismatch IS NULL AND f.rating IS NOT NULL));
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed;
END;
$$;
COMMENT ON FUNCTION dw.refresh_fact_review_sentiment(bigint[]) IS 'Đồng bộ nhãn, điểm cảm xúc và cờ lệch pha từ dw.fact_review_sentiment sang dw.fact_review (khóa rỗng = tất cả); trả về số dòng đã đổi';

SELECT dw.refresh_fact_review_sentiment(NULL);

-- ---------------------------------------------------------------- G4: cảnh báo
ALTER TABLE dw.fact_alert ADD COLUMN IF NOT EXISTS recommended_action text;
ALTER TABLE dw.fact_alert ADD COLUMN IF NOT EXISTS responsible_department text;
COMMENT ON COLUMN dw.fact_alert.recommended_action IS 'Đề xuất hành động mẫu theo khía cạnh và chỉ số (do T7 sinh)';
COMMENT ON COLUMN dw.fact_alert.responsible_department IS 'Bộ phận phụ trách xử lý: Product Manager, Customer Success, Đội kỹ thuật, Marketing và Kinh doanh, Ban điều hành';

CREATE OR REPLACE VIEW dw.v_alert_open AS
SELECT a.alert_key,
       a.detected_at,
       t.full_date AS detected_date,
       p.platform_name,
       asp.aspect_name,
       a.metric_name,
       a.metric_value,
       a.threshold,
       a.status,
       a.recommended_action,
       a.responsible_department,
       a.notified_at
FROM dw.fact_alert a
JOIN dw.dim_platform p ON p.platform_key = a.platform_key
JOIN dw.dim_time     t ON t.time_key     = a.time_key
LEFT JOIN dw.dim_aspect asp ON asp.aspect_key = a.aspect_key
WHERE a.status <> 'da_xu_ly';
COMMENT ON VIEW dw.v_alert_open IS 'View cảnh báo chưa xử lý (status khác da_xu_ly) kèm tên nền tảng, khía cạnh, đề xuất hành động và bộ phận phụ trách';
