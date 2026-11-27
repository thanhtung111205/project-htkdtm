# Kết quả tập vàng gán nhãn người (27/11/2026)

## Kiểm tra dữ liệu gán nhãn

- Năm thành viên, mỗi người gán 280 dòng; tổng cộng 1.200 `item_id` duy nhất.
- Mỗi dòng có một nhãn cảm xúc hợp lệ. 200 mẫu được hai người cùng gán.
- Với tệp của Thái Anh, 280/280 nhãn cảm xúc đã điền; mã mẫu và văn bản đã được đối chiếu với `gold_texts_1200.csv`. Ba ô văn bản lệch nguồn đã được khôi phục, giữ nguyên nhãn đã gán.
- Tập gold của người có 1.144 dòng đồng thuận sau khi loại 27 trường hợp bất đồng và 29 dòng `Bỏ qua`.

Các tệp Excel và CSV nguồn chứa nội dung đánh giá nằm ngoài Git, chia sẻ qua kênh riêng của nhóm.

## Độ nhất quán nhãn

| So sánh | Số mẫu | Cohen's kappa | Tỷ lệ khớp thô |
|---|---:|---:|---:|
| Người với người trên mẫu gán đôi | 200 | 0,789 | 86,5% |
| Nhãn người với nhãn LLM | 1.400 lượt gán | 0,7017 | 81,29% |

Kappa người–LLM vượt ngưỡng tối thiểu 0,50 trong đề cương. Chỉ số này không thay cho đánh giá F1 của mô hình trên nhãn người.

## M1 trên nhãn người

Đánh giá ba lớp trên 1.144 mẫu đồng thuận; các nhãn `Bỏ qua` và bất đồng không được tính.

| Mô hình | Macro-F1 | Accuracy |
|---|---:|---:|
| LLM zero-shot | 0,7506 | 0,8086 |
| TF-IDF + Logistic Regression | 0,6594 | 0,7273 |
| PhoBERT | 0,6769 | 0,7579 |

PhoBERT chưa đạt ngưỡng macro-F1 tối thiểu 0,70 đặt trong tiêu chí T2.1. Cần báo cáo kết quả thật và cải thiện mô hình; không thay số bằng kết quả đo trên nhãn LLM.

## Phủ nhãn khía cạnh

Số mẫu có nhãn khía cạnh người gán (có thể gồm các lượt gán trùng): Technical 471, Academic 308, Customer Service 58, Pricing 169. Customer Service có ít mẫu nhất; cần nêu hạn chế này khi diễn giải F1 theo khía cạnh.
