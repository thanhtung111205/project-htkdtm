# Rà soát `dim_event` (TA2)

Ngày rà soát: 26/11/2026. Múi giờ: Việt Nam.

## Kết quả đối chiếu seed mới

`data/raw/context/dim_event_seed.csv` có 347 dòng: 282 mốc phiên bản lấy từ ngày đánh giá đầu tiên có nhắc phiên bản, 28 ngày sale cố định, 7 ngày khai giảng và 30 dòng `confidence=can_kiem_tra`. Dòng phiên bản không phải ngày phát hành thật; bộ chuẩn bị giữ chúng ở trạng thái `needs_review=true`. Ngày khai giảng không được đổi tên thành mùa thi. Seed không có sự cố dịch vụ nào đã xác minh.

Đã rà riêng cả 30 dòng cần kiểm tra, ghi quyết định ở bảng dưới. Kết quả giữ 8 sự kiện chuẩn hóa; các bài trùng được gộp, bài gọi vốn/tài chính hoặc không chứng minh được sự cố bị loại. Học bổng S-Global, hai lần công bố tính năng ELSA và cập nhật khóa tiếng Nhật giữ `needs_review=true` vì chưa xác minh ngày áp dụng thực tế hoặc thời hạn.

| ID seed | Quyết định | Lý do / mốc dùng | Nguồn công khai |
|---:|---|---|---|
| 65 | Bỏ | Tin gọi vốn Do Ventures, không thuộc bốn loại sự kiện trong schema. | [VnEconomy](https://vneconomy.vn/do-venture-rot-von-vao-mot-nen-tang-edtech-viet.htm) |
| 76 | Giữ, sửa ngày | Khuyến mãi HOCMAI–MoMo: 20/10–20/11/2021. | [VnExpress](https://vnexpress.net/hocmai-uu-dai-hoc-phi-chi-10-000-dong-khi-thanh-toan-qua-momo-4377196.html) |
| 80 | Giữ, sửa ngày | Khuyến mãi HOCMAI–ShopeePay: 01–30/11/2021. | [VietnamNet](https://vietnamnet.vn/co-hoi-giam-50-hoc-phi-tren-hocmai-va-icankid-791175.html) |
| 105 | Bỏ | Bài về vòng gọi vốn 2 triệu USD, không phải cập nhật/dịch vụ. | [VUIHOC](https://www.vuihoc.vn/tin/VUIHOC-goi-von-2-trieu-USD-1397.html) |
| 108 | Bỏ | Bài khác đưa tin cùng vòng gọi vốn 2 triệu USD với ID 105. | [VUIHOC](https://www.vuihoc.vn/tin/VUIHOC-goi-von-2-trieu-USD-1397.html) |
| 124 | Bỏ | Bài tổng hợp các vòng gọi vốn, không phải sự kiện sản phẩm. | [Diễn đàn Doanh nghiệp](https://diendandoanhnghiep.vn/startup-giao-duc-vuihoc-3-nam-lien-tiep-goi-von-thanh-cong-10037898.html) |
| 129 | Bỏ | Vòng Series A 6 triệu USD, không phải sự kiện sản phẩm. | [VnEconomy](https://vneconomy.vn/startup-cong-nghe-giao-duc-viet-duoc-rot-them-6-trieu-usd.htm) |
| 135 | Bỏ | Tin gọi vốn Series C của ELSA. | [Tia Sáng](https://tiasang.com.vn/elsa-goi-von-thanh-cong-23-trieu-usd-4967995.html) |
| 139 | Giữ, cần rà tiếp | Tính năng tạo hội thoại AI; lấy ngày bài công bố 27/10/2023, chưa xác nhận ngày rollout. | [VnExpress](https://vnexpress.net/elsa-speak-them-tinh-nang-tu-tao-hoi-thoai-voi-ai-4670022.html) |
| 140 | Gộp vào ID 139 | Cùng tính năng AI, bị phân loại nhầm thành gọi vốn. | [Dân trí](https://dantri.com.vn/tim-kiem/elsa%2Bai.htm) |
| 158 | Giữ, cần rà tiếp | Học bổng S-Global 2 hỗ trợ đến 65%; nguồn xác nhận mức hỗ trợ nhưng không cho thời hạn áp dụng. | [VTV](https://vtv.vn/giao-duc/nang-cap-hoc-bong-s-global-2-cho-ielts-va-giao-tiep-truc-tuyen-20240416175740838.htm) |
| 200 | Bỏ | Bài giới thiệu giá trị doanh nghiệp; không có ưu đãi mua/học cụ thể. | HTV, bài phân tích doanh nghiệp theo tiêu đề trong seed |
| 207 | Bỏ | Bài giới thiệu định giá Duolingo; không phải chương trình khuyến mãi. | Thể thao & Văn hóa, bài phân tích doanh nghiệp theo tiêu đề trong seed |
| 213 | Gộp vào ID 215 | Cùng đợt công bố phiên bản AI thế hệ mới; ngày 13/02 trong seed không khớp bài công bố có ngày rõ. | [Dân trí](https://dantri.com.vn/giao-duc/ung-dung-elsa-speak-tung-ra-phien-ban-ai-the-he-moi-20250217174948066.htm) |
| 215 | Giữ, cần rà tiếp | Phiên bản AI mới được công bố ngày 18/02/2025; chưa xác nhận ngày rollout đầy đủ. | [Dân trí](https://dantri.com.vn/giao-duc/ung-dung-elsa-speak-tung-ra-phien-ban-ai-the-he-moi-20250217174948066.htm) |
| 229 | Gộp vào sự kiện Duolingo Chess | Bài đăng sau ngày beta; mốc beta iOS là 22/04/2025. | [Axios](https://www.axios.com/local/pittsburgh/2025/04/22/duolingo-chess-learning-app-launch) |
| 231 | Gộp vào sự kiện Duolingo Chess | Bản tin tuần lặp lại tin ra mắt khóa cờ, không phải tính năng riêng. | [Duolingo Blog](https://blog.duolingo.com/chess-course/) |
| 234 | Bỏ | Bài nói về doanh thu/tăng trưởng công ty, không phải cập nhật sản phẩm. | Lao Động, bài tài chính theo tiêu đề trong seed |
| 237 | Gộp vào sự kiện Duolingo Chess | Cùng đợt triển khai khóa cờ; không tạo thêm sự kiện riêng. | [Duolingo Blog](https://blog.duolingo.com/chess-course/) |
| 258 | Bỏ | Xin lỗi về nội dung câu học, không phải sự cố vận hành hay gián đoạn dịch vụ. | [Tuổi Trẻ](https://tuoitre.vn/ung-dung-hoc-ngon-ngu-duolingo-xin-loi-vi-noi-jk-rowling-xau-tinh-20250824095128688.htm) |
| 259 | Bỏ | Bài nói về tính năng Google Dịch, không phải khuyến mãi của Duolingo. | Thế Giới Số, bài về Google Dịch theo tiêu đề trong seed |
| 261 | Bỏ | Bản tin lẫn tin tuyển dụng và sản phẩm Google; không xác nhận phát hành Duolingo. | Advertising Vietnam, bản tin tuần theo tiêu đề trong seed |
| 272 | Giữ, cần rà tiếp | Bài về anime xác nhận trùng thời điểm mở rộng khóa tiếng Nhật; giữ làm mốc công bố 10/10/2025, chưa rõ ngày khóa học được triển khai cho mọi người học. | [Tuổi Trẻ](https://tuoitre.vn/duolingo-ra-mat-anime-dau-tay-cu-xanh-cuc-suc-lan-san-man-anh-nhat-ban-20251010112244568.htm), [video chính thức](https://www.youtube.com/watch?v=lHcUJ2vcR2Y) |
| 286 | Bỏ | Mở rộng thị trường Hồng Kông là mở rộng kinh doanh, không thuộc loại sự kiện đã chốt. | [VietnamPlus](https://www.vietnamplus.vn/ung-dung-hoc-tieng-anh-bang-ai-elsa-speak-chinh-thuc-gia-nhap-thi-truong-hong-kong-post1087230.vnp) |
| 289 | Bỏ | Video/marketing trong bản tin tuần, không phải cập nhật ứng dụng. | MarketingAI, bản tin tuần theo tiêu đề trong seed |
| 290 | Bỏ | Bài giới thiệu phiên bản PC miễn phí, không nêu chương trình khuyến mãi có thời hạn. | Viettel Store, bài giới thiệu sản phẩm theo tiêu đề trong seed |
| 302 | Bỏ | Bài giải thích Duolingo Max và giá, không phải ngày ra mắt hay đợt giảm giá. | [CellphoneS](https://cellphones.com.vn/sforum/duolingo-max) |
| 305 | Bỏ | Bài hướng dẫn xử lý lỗi chung, không chứng minh có sự cố thực tế. | [CellphoneS](https://cellphones.com.vn/sforum/duolingo-bi-loi) |
| 310 | Giữ, sửa loại và ngày | Chiến dịch khôi phục streak miễn phí diễn ra 01–30/06/2026; đây là quyền lợi có thời hạn, phân loại `khuyen_mai`. | [Kênh YouTube chính thức Duolingo](https://www.youtube.com/watch?v=IlL6SUH-dVU) |
| 324 | Bỏ | Thương vụ mua studio, không phải sự kiện sản phẩm/dịch vụ. | [Advertising Vietnam](https://advertisingvietnam.com/article/duolingo-mua-lai-animade-vi-sao-thuong-hieu-van-dat-cuoc-vao-suc-sang-tao-con-nguoi-giua-thoi-ai) |

## Sự kiện mùa thi đã xác minh

Các dòng `mua_vu_khai_giang` trong seed là ngày khai giảng, không phải kỳ thi nên đã loại thay vì gán sai loại. Bổ sung hai kỳ thi tốt nghiệp THPT với ngày thi chính thức (không tính ngày làm thủ tục/dự phòng): [2025, 26–27/06](https://vqa.moet.gov.vn/vi/news/tin-tuc-su-kien/huong-dan-to-chuc-ky-thi-tot-nghiep-trung-hoc-pho-thong-nam-2025-178.html) và [2026, 11–12/06](https://xaydungchinhsach.chinhphu.vn/cong-van-1257-bgddt-qlcl-huong-dan-to-chuc-ky-thi-tot-nghiep-thpt-2026-119260319150811.htm).

## Tạo dữ liệu nạp

Hai script dùng seed cục bộ và tạo CSV trong `data/clean/`; không đưa dữ liệu thô hoặc CSV lên Git. Bộ chuẩn bị tạo 320 dòng: 282 phiên bản có ngày proxy và `needs_review=true`; 28 ngày sale toàn thị trường; 8 sự kiện đã rà (bao gồm 2 kỳ thi); trong đó 34 dòng có thể dùng ngay, 286 dòng còn chờ rà.

```powershell
python src/etl/load/prepare_events.py
python src/etl/load/load_events.py --csv data/clean/dim_event_seed.csv
```

Loader xác thực loại/ngày/nền tảng, bỏ trùng khi chạy lại và không tự xóa sự kiện. Cần nạp `dw.dim_platform` trước. Máy hiện chưa có `.env`/`DATABASE_URL`, nên chưa thể ghi hoặc đếm trong PostgreSQL; báo cáo leader cho biết bảng đang có 0 dòng. Sau khi có kết nối, chạy hai lệnh trên rồi kiểm tra số dòng và khóa nền tảng trong DB.
