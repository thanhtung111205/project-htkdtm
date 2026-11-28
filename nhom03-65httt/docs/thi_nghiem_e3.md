# Thí nghiệm E3: Đối chiếu dữ liệu thu thập với thực tế bên ngoài

**Người thực hiện:** Hoàng Anh (Nhóm 03, Lớp 65HTTT)  
**Đề tài:** Hệ thống phân tích kinh doanh EduVision BI cho 9 nền tảng E-learning  
**Căn cứ đề cương:** Mục 8.3 — Thí nghiệm đối chiếu độ tin cậy của mẫu dữ liệu  

---

## 1. Mục đích thí nghiệm

Dữ liệu đánh giá người dùng (reviews) được thu thập từ các kho ứng dụng (Google Play, App Store) là nguồn thông tin chính để tính toán các chỉ số sức khỏe thương hiệu (BHI), chỉ số cảm xúc (Sentiment Index) và phân tích khía cạnh (ABSA). 

Thí nghiệm E3 nhằm mục đích:
1. **Phần (a):** Đánh giá tính đại diện và độ lệch (bias) của mẫu đánh giá thu thập được so với số sao và lượng đánh giá tổng thể công bố trên các kho ứng dụng.
2. **Phần (b):** Đối chiếu xu hướng số lượng đánh giá mới phát sinh hàng tháng với mức độ quan tâm tìm kiếm thực tế của người dùng trên Google Trends nhằm kiểm chứng tính quy luật của lưu lượng dữ liệu.

---

## 2. Nguồn dữ liệu sử dụng

1. **CSDL Data Warehouse (PostgreSQL):**
   - Bảng `dw.fact_review`: 28.718 bản ghi đánh giá chi tiết kèm số sao và thời gian.
   - Bảng chiều `dw.dim_platform` (9 nền tảng) và `dw.dim_source` (kho ứng dụng: `google_play`, `app_store_vn`).
   - View `dw.v_platform_month`: Tổng hợp số lượng đánh giá mới theo tháng (`new_review_count`).
   - Bảng `clean.trends_monthly` (migration 0007): Mức độ quan tâm tìm kiếm theo tháng từ Google Trends (`interest_self_scaled` từ 0 đến 100).
2. **Dữ liệu ngữ cảnh bên ngoài:**
   - Tệp `data/raw/context/app_info.csv`: Dữ liệu công bố chính thức về điểm sao trung bình (`score`) và tổng số lượt đánh giá (`ratings`) cào từ Google Play Store và Apple App Store Việt Nam.

---

## 3. Phần (a): Đối chiếu mẫu thu thập với số sao công bố trên cửa hàng

### 3.1. Phương pháp thực hiện
- Trích xuất từ `dw.fact_review` số sao trung bình và phân bố sao của từng nền tảng theo từng kho ứng dụng (`google_play` và `app_store_vn`).
- Lấy ảnh chụp mới nhất của từng ứng dụng từ `app_info.csv`.
- Tính độ chênh lệch: $\Delta = \text{Sao TB mẫu} - \text{Sao công bố}$.

### 3.2. Bảng kết quả thực tế từ CSDL

| Nền tảng | Cửa hàng | Sao TB mẫu | Sao công bố | Chênh lệch | Cỡ mẫu | Số lượt công bố |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| Busuu | app_store_vn | 4.62 | 4.72 | -0.10 | 500 | 9,027 |
| Busuu | google_play | 4.49 | 4.75 | -0.26 | 2,079 | 1,253,171 |
| DUOLINGO | app_store_vn | 3.79 | 4.69 | -0.90 | 477 | 785,473 |
| DUOLINGO | google_play | 4.25 | 4.70 | -0.45 | 3,020 | 51,990,387 |
| ELSA Speak | app_store_vn | 2.77 | 4.74 | -1.97 | 499 | 284,426 |
| ELSA Speak | google_play | 3.59 | 4.51 | -0.92 | 3,020 | 1,023,646 |
| HOCMAI | app_store_vn | 3.02 | 4.25 | -1.23 | 169 | 1,457 |
| HOCMAI | google_play | 3.46 | 3.28 | +0.18 | 2,453 | 6,781 |
| Khan Academy | app_store_vn | 3.73 | 4.61 | -0.88 | 174 | 3,850 |
| Khan Academy | google_play | 3.04 | 2.71 | +0.33 | 860 | 173,948 |
| MONKEY | app_store_vn | 3.65 | 4.57 | -0.92 | 500 | 83,607 |
| MONKEY | google_play | 3.86 | 4.30 | -0.43 | 3,005 | 102,524 |
| Memrise | app_store_vn | 4.21 | 4.79 | -0.58 | 500 | 53,785 |
| Memrise | google_play | 4.61 | 4.65 | -0.04 | 3,002 | 1,571,146 |
| Quizlet | app_store_vn | 3.64 | 4.83 | -1.20 | 500 | 100,853 |
| Quizlet | google_play | 4.21 | 4.59 | -0.38 | 3,004 | 926,667 |
| VUIHOC | app_store_vn | 3.68 | 4.33 | -0.66 | 428 | 6,909 |
| VUIHOC | google_play | 3.37 | 4.15 | -0.77 | 3,020 | 19,833 |

### 3.3. Kết luận phân tích (3 điểm chính)
1. **Xu hướng lệch khắt khe hơn:** Ở 16/18 cặp cửa hàng - nền tảng, số sao trung bình của mẫu thu thập đều thấp hơn điểm công bố toàn thời gian trên cửa hàng (chênh lệch từ -0.04 đến -1.97 sao). Nguyên nhân cốt lõi là mẫu cào tập trung vào các đánh giá mới nhất theo thời gian (recency bias), nơi người học thường chủ động lên kho ứng dụng để phản ánh khi gặp lỗi cập nhật, giao diện giật lag hoặc khúc mắc về giá/thanh toán.
2. **Nền tảng lệch nhiều nhất:** ELSA Speak trên App Store Việt Nam ghi nhận mức chênh lệch lớn nhất (-1.97 sao, mẫu chỉ đạt 2.77 so với 4.74 sao công bố), kế tiếp là HOCMAI trên App Store (-1.23 sao) và Quizlet trên App Store (-1.20 sao), phản ánh sự bức xúc của học viên với các bản cập nhật phiên bản gần đây.
3. **Ảnh hưởng tới cách diễn giải KPI:** Điểm sao công bố trên cửa hàng mang tính tích lũy lịch sử với quán tính rất cao từ hàng trăm nghìn hoặc hàng chục triệu lượt đánh giá cũ, che giấu các vấn đề hiện tại. Do đó, các chỉ số BHI và CSI tính toán từ mẫu dữ liệu gần đây của EduVision BI phản ánh chân thực và nhạy bén hơn sức khỏe thương hiệu thực tế của sản phẩm.

---

## 4. Phần (b): Số đánh giá mới so với mức quan tâm Google Trends

### 4.1. Phương pháp thực hiện
- Trích xuất số lượng đánh giá mới hàng tháng (`new_review_count`) từ `dw.v_platform_month` ghép nối với chỉ số tìm kiếm `interest_self_scaled` từ `clean.trends_monthly` theo từng tháng.
- Lọc điều kiện:
  - Bỏ các tháng chưa kết thúc (`is_partial = false`).
  - Chỉ giữ các tháng có lưu lượng đánh giá đáng kể ($\ge 5$ đánh giá).
  - Yêu cầu chuỗi thời gian tối thiểu 6 tháng để đảm bảo ý nghĩa thống kê; dưới 6 tháng ghi "không đủ dữ liệu".
- Do `interest_self_scaled` được Google chuẩn hóa riêng cho từng nền tảng (thang điểm 0–100 theo đỉnh cao nhất của chính từ khóa đó), ta tính hệ số tương quan thứ hạng Spearman ($\rho$) và giá trị $p$-value riêng cho từng nền tảng qua các tháng, tuyệt đối không so sánh chéo giá trị mức quan tâm giữa các nền tảng khác nhau.

### 4.2. Bảng kết quả thực tế từ CSDL

| Nền tảng | Số tháng | Spearman rho | p-value | Trạng thái |
| :--- | :---: | :---: | :---: | :--- |
| Busuu | 94 | +0.4282 | 1.6713e-05 | đủ dữ liệu |
| DUOLINGO | 18 | -0.2507 | 3.1575e-01 | đủ dữ liệu |
| ELSA Speak | 45 | +0.3981 | 6.7581e-03 | đủ dữ liệu |
| HOCMAI | 68 | +0.5391 | 2.1071e-06 | đủ dữ liệu |
| Khan Academy | 41 | +0.8793 | 3.8956e-14 | đủ dữ liệu |
| MONKEY | 73 | +0.7800 | 4.1993e-16 | đủ dữ liệu |
| Memrise | 78 | +0.4338 | 7.2492e-05 | đủ dữ liệu |
| Quizlet | 49 | +0.7262 | 3.5080e-09 | đủ dữ liệu |
| VUIHOC | 58 | +0.6718 | 7.7694e-09 | đủ dữ liệu |

### 4.3. Kết luận phân tích (3 điểm chính)
1. **Tương quan đồng biến chặt chẽ:** 8/9 nền tảng thể hiện mối tương quan đồng biến dương có ý nghĩa thống kê cực kỳ cao ($p < 0.01$). Trong đó, Khan Academy ($\rho = +0.88$), MONKEY ($\rho = +0.78$), Quizlet ($\rho = +0.73$) và VUIHOC ($\rho = +0.67$) có mức độ đồng pha rất mạnh giữa nhu cầu tìm kiếm trên Google và lượng học viên tương tác để lại đánh giá trên app.
2. **Trường hợp ngoại lệ DUOLINGO:** DUOLINGO có hệ số tương quan nghịch nhẹ ($\rho = -0.25$) nhưng không có ý nghĩa thống kê ($p = 0.316 > 0.05$). Điều này phản ánh từ khóa "Duolingo" đã trở thành thương hiệu phổ thông với lượng tìm kiếm ổn định quanh năm, trong khi dữ liệu đánh giá tại thị trường Việt Nam chỉ đột biến vào các chiến dịch cụ thể hoặc sự kiện tính năng mới.
3. **Ý nghĩa thực tiễn cho dự báo M3:** Mức quan tâm trên Google Trends phản ánh nhu cầu tìm kiếm tự nhiên của thị trường và đóng vai trò như một biến ngoại sinh (leading indicator) quan trọng cho mô hình dự báo M3 (LightGBM/Ridge), giúp dự báo trước lưu lượng đánh giá và mức độ thâm nhập thị trường của từng ứng dụng.

---

## 5. Hạn chế của thí nghiệm

1. **Mẫu thu thập không ngẫu nhiên tuyệt đối (Sampling Bias):** Cơ chế API kho ứng dụng ưu tiên trả về các đánh giá mới nhất và đánh giá có độ tương tác cao (most helpful), không phản ánh phân phối ngẫu nhiên đều của toàn bộ tập người dùng.
2. **Đặc thù chuẩn hóa của Google Trends:** Chỉ số `interest_self_scaled` là số liệu tương đối theo chuỗi thời gian của riêng từ khóa, chịu ảnh hưởng bởi thuật toán lấy mẫu ngẫu nhiên của Google nên có thể dao động nhẹ giữa các lần truy vấn.
3. **Tính chất ảnh chụp thời điểm của dữ liệu cửa hàng:** Tệp `app_info.csv` là ảnh chụp tại một thời điểm cố định (18/11/2026), không phải chuỗi biến động liên tục theo ngày.
