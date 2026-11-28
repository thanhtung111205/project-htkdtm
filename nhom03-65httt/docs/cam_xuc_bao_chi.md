# Chấm cảm xúc báo chí (TA4)

## Trạng thái ngày 28/11/2026

Trong workspace hiện tại, `data/raw/news/news.csv` có 413 bài và 404 `title_hash` duy nhất. Áp dụng regex `title_match` trong `config/platforms.yml` giữ 122 bài, bỏ 291 bài; 122 dòng giữ không trùng theo `(platform, title_hash)`. Review mới nhất ghi 433 bài và giữ 125, nhưng tệp CSV có trong nhánh này vẫn là bản 413 bài nên chưa thể tái lập con số mới.

Máy hiện tại chưa có `.env`, dịch vụ PostgreSQL, hoặc checkpoint M1 trong `models/`. Vì vậy chưa thể chạy chấm M1, xác nhận số dòng trong `dw.fact_news_sentiment`, hay báo KPI-07. Không coi việc chấm/ghi CSDL là đã hoàn tất. Script đã được sửa để mặc định bỏ qua các khóa fact đã tồn tại; chỉ cập nhật/ghi đè khi truyền `--replace` (bí danh `--replace-existing`).

Khi có CSV 433 bài khớp review, CSDL và checkpoint M1, truyền scorer M1 theo hợp đồng trả về `sentiment_score` trong `[-1, 1]`, `sentiment_label` thuộc `tich_cuc|trung_tinh|tieu_cuc` và `confidence` trong `[0, 1]`; sau đó chạy:

```powershell
$env:TA4_SCORER = "package.module:function"
$env:TA4_MODEL_NAME = "M1"
$env:TA4_MODEL_VERSION = "<phiên-bản>"
python src/ml/news/score_news.py
```

Nếu bỏ `TA4_SCORER`, script dùng baseline từ khóa và ghi đúng tên `TA4_lexicon_baseline` vào `dw.dim_model`; kết quả chỉ dùng kiểm tra luồng, không thay thế M1. Script chỉ giữ tiêu đề khớp tên nền tảng theo `config/platforms.yml`, ghi vào `dw.fact_news_sentiment` bằng khóa `(source_key, article_id, platform_key)`, và mặc định bỏ qua dòng đã có. Chỉ truyền `--replace` khi chủ động cho phép ghi đè.

## Hạn chế cần báo cáo sau khi có dữ liệu

- Chỉ dùng tiêu đề; không lưu hay phân tích toàn văn bài báo.
- Cỡ mẫu nhỏ và lệch nền tảng; báo cáo đề cương nêu khoảng 123 bài liên quan trong 433 bài, còn nhóm quốc tế chỉ có 4 bài.
- Kết quả chỉ phục vụ phân tích khám phá; không suy rộng ra toàn bộ truyền thông.
- Cần làm mới CSV để số bài khớp 433/125 như review mới nhất, sau đó ghi lại số đọc/giữ/chấm thực tế từ lượt chạy M1.
