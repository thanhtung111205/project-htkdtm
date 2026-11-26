# Thí nghiệm E2: điểm sao và cảm xúc quanh sự kiện

## Trạng thái ngày 26/11/2026

Chưa có kết quả định lượng. Seed sự kiện mới hiện có 347 dòng; nhánh TA2 đã rà 30 dòng đánh dấu, tạo 320 sự kiện chuẩn hóa, trong đó 34 dòng `needs_review=false` có thể dùng cho phân tích và 286 dòng còn chờ xác minh ngày. Chưa có `BoGanNhan_ThaiAnh.xlsx`, tệp 3.775 nhãn khía cạnh, `.env`/kết nối CSDL hoặc trọng số M1/M2. Vì vậy chưa thể tạo `fact_review_aspect` hay truy vấn `dw.fact_review` để tính E2.

Các cập nhật ELSA có ngày công bố nhưng chưa xác nhận rollout, học bổng chưa có thời hạn, cập nhật khóa tiếng Nhật chưa có ngày rollout và mọi mốc phiên bản suy ra từ đánh giá đều còn `needs_review=true`; script E2 loại chúng ra. Danh sách nguồn và quyết định nằm trong nhánh TA2 tại `docs/ra_soat_dim_event.md`.

Không điền số độ trễ, biên độ, tỷ lệ lệch pha hoặc trích dẫn đánh giá khi chưa chạy trên dữ liệu thật. Baseline từ khóa chưa được dùng làm kết quả M2.

## Phân tích cần hoàn tất

Sau khi có M2 và seed đã rà, tính cho từng sự kiện đủ tin cậy:

- số sao trung bình và Sentiment Index trước/sau sự kiện trên cửa sổ thời gian chung;
- độ trễ đến ngày đầu có tín hiệu thay đổi theo ngưỡng đã nêu trước;
- biên độ thay đổi của hai chỉ số;
- tỷ lệ lệch pha giữa sao cao/cảm xúc tiêu cực hoặc sao thấp/cảm xúc tích cực;
- một vài ca lệch pha với nội dung đã rà và che thông tin cá nhân.

Script `src/ml/aspects/experiment_e2.py` đã cố định cửa sổ 14 ngày trước/sau, tín hiệu đổi sao từ 0,5 điểm hoặc SI từ 10 điểm với ít nhất 5 đánh giá/ngày, và tiêu chí lệch pha (4–5 sao với cảm xúc tiêu cực hoặc 1–2 sao với cảm xúc tích cực). SI được tính từ trung bình điểm cảm xúc M2 theo khía cạnh của mỗi đánh giá, nhân 100. Đây là định nghĩa vận hành ban đầu cần ghi rõ khi báo cáo.

Script chỉ đọc sự kiện `needs_review=false`; hai tệp đầu ra ở `data/reports/` gồm số liệu tổng hợp và tối đa năm ca lệch pha mỗi sự kiện/nền tảng. Tệp ca lệch pha có nội dung đánh giá người dùng, bị Git bỏ qua và phải được rà, che thông tin cá nhân trước khi đưa trích dẫn ngắn vào báo cáo.
