# TA4: Cảm xúc tiêu đề báo chí

## Phạm vi và trạng thái

Tập nguồn có 413 tiêu đề, không có toàn văn bài báo. Baseline trước đây trả khoảng 93% trung tính; đây chỉ là xác nhận luồng, không phải độ chính xác hay kết quả M1.

Sau lọc liên quan, số liệu TA4 của nhóm nền tảng quốc tế gồm **67 bài về Duolingo**, không phải 4. Con số 4 là số dòng trong snapshot riêng `data/raw/news_intl/news.csv`, có phạm vi khác; không dùng nó làm tổng số bài Duolingo. Tệp nguồn `data/raw/news/news.csv` còn gồm các kết quả tìm kiếm thô nên số dòng gắn `DUOLINGO` trước lọc không phải số bài liên quan đã giữ.

M1 chưa được kiểm định trên tiêu đề. Tập vàng TA4 gồm 50 tiêu đề được chọn có chủ đích từ năm nền tảng: 22 tích cực, 20 trung tính, 8 tiêu cực. Đây là tập dò lỗi nhỏ, không đại diện phân bố báo chí và không dùng để huấn luyện. Tệp `src/ml/sentiment/fixtures/ta4_news_title_gold_50.csv` chỉ lưu `title_hash`, nền tảng và nhãn; ghép với `data/raw/news/news.csv` khi đánh giá.

Quy ước gán nhãn là cảm xúc mà tiêu đề thể hiện đối với nền tảng: tiêu đề tường thuật một sự kiện hoặc chiến dịch nhưng không bày tỏ đánh giá được gán trung tính; lời khen rõ ràng gán tích cực; chỉ trích hoặc sự cố gây bất lợi được nêu rõ gán tiêu cực. Ví dụ, `Duolingo thông báo 'cú xanh đã chết'` được gán trung tính vì tiêu đề nói về chiến dịch linh vật, không phải đánh giá tiêu cực về ứng dụng.

## Đánh giá M1

Sau khi có checkpoint tại `models/m1_phobert_sentiment/`, chạy từ thư mục `nhom03-65httt`:

```bash
python src/ml/sentiment/evaluate_news_titles.py
```

Có thể truyền `--titles`, `--labels` hoặc `--model-dir` nếu dùng đường dẫn khác. Báo cáo macro-F1 và F1 từng lớp; không nhập kết quả này chung với đánh giá M1 trên review vì tiêu đề báo là miền dữ liệu khác.

## Giới hạn

- Tiêu đề ngắn và thiếu ngữ cảnh bài viết; một từ như “chết” không đủ để kết luận bài viết thể hiện thái độ tiêu cực.
- Mẫu 50 được chọn để có đủ trường hợp dễ và khó, không dùng để ước lượng tỷ lệ cảm xúc của toàn bộ báo chí.
- Chỉ dùng nhãn M1 sau khi chạy scorer; baseline keyword 93% trung tính không được ghi là kết quả M1.
