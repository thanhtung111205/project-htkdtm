# Thí nghiệm E4: mô hình dự báo M3 (Nhóm 03)

Mọi số dưới đây là số đo thật từ `python src/ml/forecast/m3_forecast.py evaluate`, chạy lúc 2026-11-27 05:00 UTC
trên dữ liệu 28.633 đánh giá trong `dw.fact_platform_period` (cảm xúc tạm tính theo số sao, xem [kpi_bhi.md](kpi_bhi.md)).
Kết quả thô lưu ở `models/e4_results.json` (ngoài Git).

## 1. Thiết lập

- **Mục tiêu**: Sentiment Index (thang -100 đến 100) và tỷ lệ tiêu cực `negative_rate` (0 đến 1) của từng nền tảng cho tháng kế tiếp. Dự báo một bước.
- **Dữ liệu**: chỉ tháng có từ 30 đánh giá (`new_review_count`). Nền tảng có dưới 24 tháng đủ điều kiện (DUOLINGO 2, Khan Academy 11) không đưa vào đánh giá và dự báo. Còn 7 nền tảng: ELSA Speak 42, MONKEY 43, VUIHOC 33, Memrise 34, Busuu 33, HOCMAI 27, Quizlet 26 tháng. "Tháng kế tiếp" là tháng sau tháng đủ điều kiện gần nhất của nền tảng đó, nên HOCMAI, Memrise và MONKEY có dự báo cho tháng cũ hơn các nền tảng còn lại.
- **Mô hình**: một hồi quy Ridge dùng chung cho các nền tảng (độ điều chuẩn cố định 1,0, đặc trưng chuẩn hóa theo tập huấn luyện), cài bằng numpy. Chưa dùng LightGBM vì mỗi nền tảng chỉ khoảng 30 đến 40 tháng.
- **Walk-forward**: với mỗi tháng kiểm định từ **2024-01**, huấn luyện chỉ trên dòng có tháng nhỏ hơn tháng đó (đã có test kiểm tra không dùng dòng nào sau tháng kiểm định), rồi dự báo tháng đó. Không xáo trộn. **116 điểm (nền tảng x tháng)** cho mỗi cấu hình.
- **Baseline**: (a) "kỳ sau giống kỳ này"; (b) trung bình trượt 3 kỳ. Hai baseline chấm trên đúng tập 116 điểm đó.
- **Chỉ số**: MAE, RMSE, tỷ lệ dự báo đúng chiều (dấu của thay đổi so với tháng trước khớp thực tế).
- **Hạt ngẫu nhiên**: `SEED = 42` được ghi trong kết quả, nhưng Ridge là nghiệm đóng nên không có thành phần ngẫu nhiên; chạy lại cho cùng kết quả.
- **Đặc trưng**: không phải cảm xúc (log số đánh giá 2 tháng trước, mùa vụ theo tháng); cảm xúc (3 giá trị trễ và trung bình 3 kỳ của chính mục tiêu, sao trung bình, tỷ lệ tích cực, chỉ số còn lại của tháng trước); sự kiện (số sự kiện `dw.dim_event` trùng tháng dự báo và tháng trước).

## 2. Kết quả (4 cấu hình và 2 baseline)

Sentiment Index:

| Cấu hình | MAE | RMSE | Đúng chiều |
|---|---|---|---|
| C1 không cảm xúc, không sự kiện | 29,27 | 34,95 | 59,5% |
| C2 có cảm xúc | 13,65 | 17,79 | 68,1% |
| C3 có sự kiện | 29,27 | 34,95 | 59,5% |
| C4 có cảm xúc và sự kiện | 13,65 | 17,79 | 68,1% |
| Baseline kỳ sau giống kỳ này | 15,56 | 19,90 | 0,0% (xem ghi chú) |
| Baseline trung bình trượt 3 kỳ | 13,84 | 17,70 | 70,7% |

Tỷ lệ tiêu cực:

| Cấu hình | MAE | RMSE | Đúng chiều |
|---|---|---|---|
| C1 không cảm xúc, không sự kiện | 0,1405 | 0,1684 | 56,9% |
| C2 có cảm xúc | 0,0666 | 0,0868 | 66,4% |
| C3 có sự kiện | 0,1405 | 0,1684 | 56,9% |
| C4 có cảm xúc và sự kiện | 0,0666 | 0,0868 | 66,4% |
| Baseline kỳ sau giống kỳ này | 0,0748 | 0,0964 | 0,9% (xem ghi chú) |
| Baseline trung bình trượt 3 kỳ | 0,0673 | 0,0856 | 71,6% |

Ghi chú: baseline "giống kỳ này" luôn dự báo không đổi nên chỉ đúng chiều khi thực tế cũng không đổi (hầu như không xảy ra); con số đó không dùng để so sánh chiều.

## 3. Nhận xét trung thực

- **Đặc trưng cảm xúc là yếu tố quyết định**: bỏ chúng (C1, C3) làm MAE tăng hơn gấp đôi (29,27 so với 13,65; 0,1405 so với 0,0666).
- **Đặc trưng sự kiện chưa đánh giá được**: `dw.dim_event` hiện có 0 dòng (việc của Thái Anh), nên cột sự kiện là hằng và C3 trùng C1, C4 trùng C2 đúng đến chữ số cuối. Không rút ra kết luận nào về tác dụng của sự kiện. Cần chạy lại E4 khi `dim_event` có dữ liệu.
- **M3 so với baseline**: M3 (C4) tốt hơn "kỳ sau giống kỳ này" ở MAE và RMSE của cả hai mục tiêu. So với trung bình trượt 3 kỳ thì **không hơn rõ rệt**: Sentiment Index MAE thấp hơn chút (13,65 so với 13,84) nhưng RMSE cao hơn (17,79 so với 17,70); tỷ lệ tiêu cực MAE 0,0666 so với 0,0673 và RMSE 0,0868 so với 0,0856; đúng chiều thấp hơn baseline này (68,1% so với 70,7%; 66,4% so với 71,6%). Chênh lệch nhỏ so với 116 điểm kiểm định nên chưa kết luận được M3 hơn trung bình trượt.
- **Nguyên nhân có thể** (chưa kiểm chứng riêng): mô hình tuyến tính chủ yếu học lại cấu trúc tự hồi quy mà trung bình trượt đã nắm; chuỗi ngắn và nhiễu (tháng đủ 30 đánh giá vẫn dao động lớn); chưa có đặc trưng ngoại sinh có sức dự báo (sự kiện trống, cảm xúc báo chí chưa có, Google Trends chưa nạp, tỷ lệ theo khía cạnh chờ M2).
- **Cảm xúc tạm tính theo số sao**: khi M1 xong và `fact_platform_period` dựng lại bằng nhãn mô hình, cần chạy lại `evaluate` và `write`.

## 4. Tái tạo

```
docker compose run --rm migrate alembic upgrade head
python src/etl/build_platform_period.py          # dựng dw.fact_platform_period
python src/ml/forecast/m3_forecast.py evaluate   # in và lưu bảng E4
python src/ml/forecast/m3_forecast.py write      # ghi dw.fact_forecast (chạy lại không trùng)
python -m pytest src/ml/forecast -q
```

`dw.fact_forecast` nhận cả dự báo walk-forward của các tháng kiểm định (có `actual_value`) lẫn dự báo tháng kế tiếp (`actual_value` rỗng). Khoảng tin cậy là dự báo ± 1,96 lần độ lệch chuẩn sai số walk-forward, cắt về 0 đến 1 với tỷ lệ tiêu cực. `actual_value` của tháng kế tiếp sẽ được điền khi chạy lại sau khi có số thực tế.
