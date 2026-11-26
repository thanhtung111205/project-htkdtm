# Chấm cảm xúc báo chí (TA4)

## Trạng thái ngày 26/11/2026

Mã chạy lại được đã được chuẩn bị tại `src/ml/news/score_news.py`. Workspace hiện không có `data/raw/news/news.csv`, PostgreSQL chưa thể kết nối vì thiếu `.env`, và mô hình M1 chưa có trong nhánh nhóm hiện tại. Vì vậy chưa thể tính số bài giữ/bỏ, chấm 413 bài, xác nhận số dòng trong `dw.fact_news_sentiment`, hay báo kết quả KPI-07. Không coi các bước này là đã hoàn tất.

Khi M1 có trong môi trường, cung cấp hàm dự đoán theo hợp đồng trả về `sentiment_score` trong `[-1, 1]`, `sentiment_label` thuộc `tich_cuc|trung_tinh|tieu_cuc` và `confidence` trong `[0, 1]`; sau đó chạy:

```powershell
$env:TA4_SCORER = "package.module:function"
$env:TA4_MODEL_NAME = "M1"
$env:TA4_MODEL_VERSION = "<phiên-bản>"
python src/ml/news/score_news.py
```

Nếu chưa có M1, script chạy baseline từ khóa có thể giải thích và ghi đúng tên `TA4_lexicon_baseline` vào `dw.dim_model`; kết quả chỉ dùng kiểm tra luồng, không thay thế mô hình M1. Script chỉ giữ tiêu đề khớp tên nền tảng theo `config/platforms.yml`, ghi vào `dw.fact_news_sentiment` bằng khóa `(source_key, article_id, platform_key)`, và cập nhật dòng hiện có khi chạy lại.

## Hạn chế cần báo cáo sau khi có dữ liệu

- Chỉ dùng tiêu đề; không lưu hay phân tích toàn văn bài báo.
- Cỡ mẫu nhỏ và lệch nền tảng; báo cáo đề cương nêu khoảng 123 bài liên quan trong 413 bài, còn nhóm quốc tế chỉ có 4 bài.
- Kết quả chỉ phục vụ phân tích khám phá; không suy rộng ra toàn bộ truyền thông.
- Cần ghi số bài giữ/bỏ thực tế sau khi chạy bộ lọc trên tệp 413 bài.
