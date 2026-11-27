# Kết quả M2 khía cạnh (TA3)

## Baseline luật từ khóa trước khi sửa

Đánh giá hiện diện khía cạnh dùng 3.775 dòng có nhãn cảm xúc hợp lệ trong tệp LLM; 225 dòng `bo_qua` bị loại. Một khía cạnh được tính là có mặt khi cột nhãn tương ứng không trống. Baseline luật từ khóa trước sửa có macro-F1 **0,528**. Sau chỉnh luật và chạy lại cùng tập, macro-F1 là **0,530**. Cả hai đều là điểm của baseline để thử luồng, không phải mô hình M2 đã huấn luyện.

| Khía cạnh | Baseline trước sửa | Baseline sau sửa | M2 đã huấn luyện |
|---|---:|---:|
| Technical (Kỹ thuật) | 0,572 | 0,572 | Chưa đo |
| Academic (Học thuật) | 0,393 | 0,393 | Chưa đo |
| Customer Service (CSKH) | 0,566 | 0,566 | Chưa đo |
| Pricing (Giá) | 0,580 | 0,591 | Chưa đo |
| Trung bình macro | 0,528 | 0,530 | Chưa đo |

Tệp `BoGanNhan_ThaiAnh.xlsx` hiện có 280 dòng đánh giá nhưng các cột nhãn trong sheet `GN_ThaiAnh` còn trống; chưa thể dùng tệp này làm tập vàng đã gán nhãn.

Các lỗi được chỉnh trong baseline: `mặc dù` không còn bị bắt thành Pricing qua `mac`; `gia đình` không còn bị bắt qua `gia`; trong `app hay bị lỗi`, `hay` được hiểu là tần suất nên khía cạnh Technical nhận sắc thái tiêu cực. Điểm sau sửa chưa được đo lại trên cùng tập.

## Baseline và API

Baseline ở `src/backend/app/services/aspects_baseline.py` dùng luật từ khóa giải thích được, tách mệnh đề quanh từ nối tương phản để giữ cảm xúc trái chiều giữa các khía cạnh. API `POST /api/v1/predict/aspects` trả `model: "keyword_baseline"` cùng các khía cạnh được nhắc; câu không có khía cạnh trả danh sách rỗng. Trường `model` giúp không nhầm kết quả baseline với M2.

Script `src/ml/aspects/score_aspects.py` có thể nạp baseline hoặc scorer M2 tương thích vào `dw.fact_review_aspect`; cần CSDL và dữ liệu đánh giá đã ETL. Script bỏ qua xung đột đang thuộc một model khác; chỉ dùng `--replace-existing` khi chủ động thay toàn bộ kết quả khía cạnh cũ cho từng đánh giá.
