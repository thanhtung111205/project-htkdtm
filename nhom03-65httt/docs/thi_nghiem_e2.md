# Thí nghiệm E2: điểm sao và cảm xúc quanh sự kiện

## Trạng thái ngày 28/11/2026

Chưa thể chạy E2 trong workspace hiện tại: không có tệp cấu hình `.env`, dịch vụ CSDL không hoạt động, và `models/` chỉ có checkpoint M2, chưa có checkpoint M1. Vì vậy chưa có kết quả M1 trong `dw.fact_review_sentiment` để đo. Không điền số độ trễ, biên độ hoặc tỷ lệ lệch pha khi chưa chạy trên dữ liệu thật. Khi có CSDL và checkpoint M1, chạy `python src/ml/aspects/experiment_e2.py`, rồi cập nhật các số liệu từ `data/reports/e2_results.csv`.

Seed có 34 sự kiện `needs_review=false`; 30/34 là ngày sale chung, chỉ 4 sự kiện gắn riêng nền tảng. E2 còn nhận hai cập nhật ELSA có ngày công bố rõ trong mô tả. Vì chưa xác minh ngày phát hành/rollout, kết quả của hai dòng này phải mang cảnh báo và chỉ dùng thăm dò; không diễn giải biến động như tác động nhân quả của bản cập nhật. Các mốc phiên bản suy ra từ đánh giá vẫn bị loại.

## Cách tính E2

`src/ml/aspects/experiment_e2.py` dùng nhãn `dw.fact_review_sentiment` của `M1_phobert`, không lấy điểm khía cạnh từ baseline M2. Sentiment Index theo `docs/kpi_bhi.md`: `SI=(P-N)/T×100`; P và N là số nhãn tích cực và tiêu cực, T là tổng đánh giá có nhãn M1, gồm cả trung tính. Nếu một đánh giá chưa có nhãn M1 thì đánh giá đó không vào T; số đánh giá có nhãn trước/sau sự kiện được xuất riêng để thấy độ phủ thực tế.

Cửa sổ vẫn là 14 ngày trước/sau. Tín hiệu đổi sao là 0,5 điểm, đổi SI là 10 điểm, cần ít nhất 5 đánh giá có số đo trong ngày. Lệch pha là 4–5 sao với nhãn M1 tiêu cực hoặc 1–2 sao với nhãn M1 tích cực. Hai cập nhật ELSA dùng ngày công bố làm mốc thay thế; cột `event_warning` trong kết quả ghi rõ ngày rollout chưa xác minh.

## Phân tích cần hoàn tất

Sau khi có cấu hình CSDL, checkpoint M1 và seed sự kiện, tính cho từng sự kiện đủ tin cậy:

- số sao trung bình và Sentiment Index trước/sau sự kiện trên cửa sổ thời gian chung;
- độ trễ đến ngày đầu có tín hiệu thay đổi theo ngưỡng đã nêu trước;
- biên độ thay đổi của hai chỉ số;
- tỷ lệ lệch pha giữa sao cao/cảm xúc tiêu cực hoặc sao thấp/cảm xúc tích cực;
- một vài ca lệch pha với nội dung đã rà và che thông tin cá nhân.

Script `src/ml/aspects/experiment_e2.py` dùng nhãn M1, tính SI theo số lượng nhãn tích cực/trung tính/tiêu cực như quy định trong `docs/kpi_bhi.md`, và xuất tên model cùng độ phủ nhãn trước/sau sự kiện. Script giữ cửa sổ 14 ngày, ngưỡng đổi sao 0,5 điểm, ngưỡng đổi SI 10 điểm và tối thiểu 5 đánh giá/ngày.

Hai tệp đầu ra ở `data/reports/` gồm số liệu tổng hợp và tối đa năm ca lệch pha mỗi sự kiện/nền tảng. Tệp ca lệch pha có nội dung đánh giá người dùng, bị Git bỏ qua và phải được rà, che thông tin cá nhân trước khi đưa trích dẫn ngắn vào báo cáo.
