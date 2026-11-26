# Rà soát `dim_event` (TA2)

Ngày rà soát: 26/11/2026. Múi giờ: Việt Nam.

## Phạm vi và kết quả

Trong workspace hiện không có `dim_event_seed.csv` đã dùng để khởi tạo bảng, và tệp `.env` kết nối PostgreSQL cũng chưa có. Vì vậy chưa thể xác định hoặc kết luận về các dòng “cần kiểm tra” trong seed gốc hay tự xác nhận số dòng trong CSDL. Theo báo cáo leader, `dw.dim_event` hiện có 0 dòng. Bảng dưới là các mốc công khai có nguồn để bổ sung; đây không phải là kết quả rà toàn bộ 347 sự kiện nêu trong đề cương.

| Loại | Bắt đầu | Kết thúc | Nền tảng | Mô tả / quyết định | `needs_review` | Nguồn |
|---|---|---|---|---|---:|---|
| `cap_nhat` | 2026-01-04 | — | ELSA Speak | Giữ làm mốc ngày công bố bản trải nghiệm ELSA mới. Bài viết nói phát hành theo từng đợt nên ngày triển khai thực tế chưa rõ; cần đối chiếu lịch sử phiên bản kho ứng dụng trước khi dùng phân tích nhân quả. | `true` | [ELSA: Discover the New ELSA Speak Experience](https://blog.elsaspeak.com/en/discover-the-new-elsa-speak-experience/) |
| `khuyen_mai` | 2026-11-24 | 2026-11-30 | ELSA Speak | Giữ. ELSA công bố đợt Black Friday áp dụng từ 24/11 đến hết 17:00 ngày 30/11/2026. | `false` | [ELSA Việt Nam: ưu đãi Black Friday](https://vn.elsaspeak.com/christmas-2025-giam-50-toan-bo-goi-elsa-speak/) |
| `mua_thi` | 2025-06-26 | 2025-06-27 | *(sự kiện chung)* | Giữ làm mốc kỳ thi tốt nghiệp THPT; đây là hai ngày coi thi chính thức, không gộp ngày làm thủ tục 25/6 hay ngày dự phòng 28/6. | `false` | [Bộ GDĐT: hướng dẫn tổ chức kỳ thi tốt nghiệp THPT 2025](https://vqa.moet.gov.vn/vi/news/tin-tuc-su-kien/huong-dan-to-chuc-ky-thi-tot-nghiep-trung-hoc-pho-thong-nam-2025-178.html) |

Chưa thêm dòng `su_co`: không có nguồn công khai đáng tin cậy về sự cố của các nền tảng trong dữ liệu được cung cấp. Không có seed gốc để rà và đánh dấu những dòng “cần kiểm tra” khác; khi nhận được seed riêng, cần ghi quyết định giữ/sửa/bỏ và nguồn cho từng dòng còn lại.

## Cách nạp

Tệp CSV riêng có thể đặt tại `data/raw/dim_event_seed.csv` với các cột `event_type,start_date,end_date,description,platform_name,needs_review`. Để đáp ứng quy tắc dữ liệu của repo, CSV chứa sự kiện thực không được commit. Script `src/etl/load/load_events.py` kiểm tra loại sự kiện, ngày tháng, khóa nền tảng và trạng thái rà soát; chạy lại không tạo dòng trùng, đồng thời cập nhật cờ `needs_review` cho sự kiện đã có.

```powershell
python src/etl/load/load_events.py --csv data/raw/dim_event_seed.csv
```

Chạy sau khi đã nạp `dw.dim_platform`. Việc ghi vào CSDL vẫn cần `.env` cục bộ hoặc `DATABASE_URL` hợp lệ.
