# Kết quả M2 khía cạnh (TA3)

## Trạng thái ngày 26/11/2026

API và baseline luật từ khóa đã được chuẩn bị. Chưa thể báo F1 hoặc kết luận M2 đạt ngưỡng vì tệp 3.775 đánh giá có nhãn và tập vàng `BoGanNhan_ThaiAnh.xlsx` chưa có trong workspace. Không dùng nhãn giả hoặc dữ liệu tự tạo để điền số liệu.

| Khía cạnh | Baseline F1 | M2 F1 |
|---|---:|---:|
| Technical (Kỹ thuật) | Chưa đo | Chưa đo |
| Academic (Học thuật) | Chưa đo | Chưa đo |
| Customer Service (CSKH) | Chưa đo | Chưa đo |
| Pricing (Giá) | Chưa đo | Chưa đo |
| Trung bình macro | Chưa đo | Chưa đo |

`src/ml/aspects/evaluate_f1.py` cung cấp phép tính F1 hiện diện riêng theo từng khía cạnh. Khi nhận dữ liệu gán nhãn, cần thống nhất định dạng nhãn/khóa mẫu và tách tập kiểm tra theo `review_id` trước khi tính điểm. Mô hình PhoBERT M2 chưa được huấn luyện: M1 và dữ liệu huấn luyện từ kênh riêng chưa được đưa vào workspace.

## Baseline và API

Baseline ở `src/backend/app/services/aspects_baseline.py` dùng luật từ khóa giải thích được, tách mệnh đề quanh từ nối tương phản để giữ cảm xúc trái chiều giữa các khía cạnh. API `POST /api/v1/predict/aspects` trả các khía cạnh được nhắc; câu không có khía cạnh trả danh sách rỗng. Đây là baseline luồng, không phải kết quả mô hình M2.

Script `src/ml/aspects/score_aspects.py` có thể nạp baseline hoặc scorer M2 tương thích vào `dw.fact_review_aspect`; cần CSDL và dữ liệu đánh giá đã ETL. Script bỏ qua xung đột đang thuộc một model khác; chỉ dùng `--replace-existing` khi chủ động thay toàn bộ kết quả khía cạnh cũ cho từng đánh giá.
