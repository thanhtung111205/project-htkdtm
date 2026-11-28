# Kết quả M2 khía cạnh (TA3)

## Baseline luật từ khóa trước khi sửa

Đánh giá hiện diện khía cạnh dùng 3.775 dòng có nhãn cảm xúc hợp lệ trong tệp LLM; 225 dòng `bo_qua` bị loại. Một khía cạnh được tính là có mặt khi cột nhãn tương ứng không trống. Baseline luật từ khóa trước sửa có macro-F1 **0,528**. Sau chỉnh luật và chạy lại cùng tập, macro-F1 là **0,530**. Cả hai đều là điểm của baseline để thử luồng, không phải mô hình M2 đã huấn luyện.

| Khía cạnh | Baseline trước sửa | Baseline sau sửa |
|---|---:|---:|
| Technical (Kỹ thuật) | 0,572 | 0,572 |
| Academic (Học thuật) | 0,393 | 0,393 |
| Customer Service (CSKH) | 0,566 | 0,566 |
| Pricing (Giá) | 0,580 | 0,591 |
| Trung bình macro | 0,528 | 0,530 |

Bản `BoGanNhan_ThaiAnh.xlsx` cũ chưa có nhãn. Tập vàng dưới đây dùng các workbook cập nhật Tùng gửi, gồm 5 người gán nhãn với 280 dòng/người.

Các lỗi được chỉnh trong baseline: `mặc dù` không còn bị bắt thành Pricing qua `mac`; `gia đình` không còn bị bắt qua `gia`; trong `app hay bị lỗi`, `hay` được hiểu là tần suất nên khía cạnh Technical nhận sắc thái tiêu cực. Điểm 0,530 ở trên là baseline đo trên nhãn LLM, không phải kết quả trên tập vàng người gán.

## PhoBERT M2 trên tập vàng người gán

Mô hình dùng `vinai/phobert-base-v2`, huấn luyện trên 3.775 dòng có nhãn khía cạnh từ LLM; loại 225 dòng `bo_qua`. Chia 15% dữ liệu huấn luyện làm validation để chọn epoch và ngưỡng hiện diện cho từng khía cạnh, sau đó huấn luyện lại trên toàn bộ 3.775 dòng trong 5 epoch. Validation macro-F1 là 0,8136; con số này chỉ dùng để chọn cấu hình.

Đánh giá cuối dùng 1.144 dòng có đồng thuận cảm xúc chung từ người gán. Không có `item_id` nào trùng giữa dữ liệu huấn luyện và tập vàng. Với từng khía cạnh, các dòng bất đồng về hiện diện được loại riêng khỏi phép tính; macro-F1 là trung bình F1 hiện diện nhị phân của 4 khía cạnh.

| Khía cạnh | Số dòng vàng | PhoBERT M2 | Baseline từ khóa |
|---|---:|---:|---:|
| Technical (Kỹ thuật) | 1.135 | 0,8277 | 0,5968 |
| Academic (Học thuật) | 1.140 | 0,7704 | 0,3229 |
| Customer Service (CSKH) | 1.142 | 0,7520 | 0,5657 |
| Pricing (Giá) | 1.141 | 0,8588 | 0,5254 |
| **Trung bình macro** | — | **0,8022** | **0,5027** |

PhoBERT M2 vượt mục tiêu macro-F1 0,65 trên tập vàng. Các chỉ số trên đo **hiện diện khía cạnh**; chưa phải chỉ số đúng/sai sắc thái cảm xúc của từng khía cạnh. Mô hình đã lưu cục bộ ở `models/m2_absa` (không đưa trọng số vào Git). Kết quả chi tiết máy đọc được ghi ở `data/ml/m2_phobert_human_gold.json`.

## Baseline và API

Baseline ở `src/backend/app/services/aspects_baseline.py` dùng luật từ khóa giải thích được, tách mệnh đề quanh từ nối tương phản để giữ cảm xúc trái chiều giữa các khía cạnh. API `POST /api/v1/predict/aspects` trả `model: "keyword_baseline"` cùng các khía cạnh được nhắc; câu không có khía cạnh trả danh sách rỗng. Trường `model` giúp không nhầm kết quả baseline với M2.

Script `src/ml/aspects/score_aspects.py` có thể nạp baseline hoặc scorer M2 tương thích vào `dw.fact_review_aspect`; cần CSDL và dữ liệu đánh giá đã ETL. Script bỏ qua xung đột đang thuộc một model khác; chỉ dùng `--replace-existing` khi chủ động thay toàn bộ kết quả khía cạnh cũ cho từng đánh giá.
