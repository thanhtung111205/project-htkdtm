-- EduVision BI - Nhóm 03: mức quan tâm Google Trends theo tháng (G12, đề cương mục 8.1 M3 và E3 phần b).
-- Nguồn: data/raw/context/trends_monthly.csv do src/etl/collectors/trends_collector.py tạo; nạp bằng src/etl/load/load_trends.py.
-- Chạy sau 06_schema_bo_sung_de_cuong.sql. Chạy lại nhiều lần không lỗi.
--
-- Hai thang đo, KHÔNG trộn lẫn:
--   interest_self_scaled      : 0 đến 100 chuẩn hóa RIÊNG từng từ khóa (chế độ --solo). Chỉ so được theo thời gian
--                               trong CÙNG một nền tảng, không so giữa các nền tảng.
--   interest_scaled_to_anchor : quy về thang của nền tảng mốc (Duolingo) trong cùng yêu cầu; so được giữa các nền tảng.
--                               Rỗng khi tệp thu thập ở chế độ --solo.
-- Google Trends lấy mẫu lại mỗi lần gọi nên số có thể đổi nhẹ giữa hai lần thu thập: loader ghi đè bằng lần mới nhất.

CREATE TABLE IF NOT EXISTS clean.trends_monthly (
    month                      date        NOT NULL,   -- ngày đầu tháng
    platform_name              text        NOT NULL,   -- khớp dw.dim_platform.platform_name
    keyword                    text        NOT NULL,   -- từ khóa đã tra trên Google Trends
    interest_self_scaled       numeric(6,2),
    interest_scaled_to_anchor  numeric(8,2),
    is_partial                 boolean     NOT NULL DEFAULT false,   -- tháng chưa kết thúc lúc thu thập; bỏ khi huấn luyện
    platform_group             text,                   -- trong_nuoc hoặc quoc_te
    loaded_at                  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (month, platform_name),
    CONSTRAINT ck_trends_month_first_day CHECK (extract(day FROM month) = 1),
    CONSTRAINT ck_trends_self_range CHECK (interest_self_scaled IS NULL OR interest_self_scaled BETWEEN 0 AND 100),
    CONSTRAINT ck_trends_anchor_nonneg CHECK (interest_scaled_to_anchor IS NULL OR interest_scaled_to_anchor >= 0)
);
CREATE INDEX IF NOT EXISTS ix_trends_monthly_platform ON clean.trends_monthly (platform_name, month);
COMMENT ON TABLE clean.trends_monthly IS
    'Mức quan tâm Google Trends theo tháng và nền tảng (G12). Đặc trưng cho M3 và đối chiếu E3(b). interest_self_scaled chỉ so trong cùng nền tảng';
