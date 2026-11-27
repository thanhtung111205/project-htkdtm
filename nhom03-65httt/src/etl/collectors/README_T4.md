Bổ sung cho [README.md](README.md) (collector Google Play và App Store).

# Collector YouTube, báo chí, Google Trends, thông tin ứng dụng (T4)

Bốn collector đọc cấu hình từ `config/platforms.yml` (mục `youtube_queries`, `news`, `trends_keyword`, `play_id`, `ios_id`),
dùng chung `collector_utils.py` (giãn cách tối thiểu 2 giây, thử lại có độ trễ tăng dần, không in khóa API).
Cài thư viện một lần: `pip install -r requirements-t4.txt` (gồm cả `requirements.txt` của collector Google Play và App Store). Chạy từ thư mục gốc kho; `--out` mặc định nằm trong `data/raw` (ngoài Git).

| Collector | Nguồn | Lệnh ví dụ | Kết quả |
|---|---|---|---|
| `youtube_collector.py` | YouTube Data API v3 chính thức, **cần `YOUTUBE_API_KEY`** trong `.env` | `python nhom03-65httt/src/etl/collectors/youtube_collector.py --only "ELSA Speak"` | `youtube_<nen_tang>.csv` (12 cột chuẩn, nạp được bằng `run_etl.py`), `youtube_videos_log.csv` |
| `news_collector.py` | Google News RSS và RSS chuyên mục giáo dục của các báo; chỉ lưu tiêu đề, tên báo, link, ngày | `python nhom03-65httt/src/etl/collectors/news_collector.py --only DUOLINGO --since 2026-10-01` | `news/news.csv` (cột khớp bảng `clean.news_article`), `news/news_summary.csv`; `--probe` kiểm tra nguồn nào chạy được |
| `trends_collector.py` | Google Trends qua `pytrends` (không chính thức, dễ bị 429) | `python nhom03-65httt/src/etl/collectors/trends_collector.py --solo --only "ELSA Speak"` | `context/trends_monthly.csv`, mỗi nền tảng mỗi tháng một dòng; tháng cuối `is_partial = True` nên bỏ khi huấn luyện |
| `app_info_collector.py` | iTunes Lookup API và `google-play-scraper` | `python nhom03-65httt/src/etl/collectors/app_info_collector.py` | `context/app_info.csv`, mỗi lần chạy là ảnh chụp theo ngày, cùng ngày không sinh trùng |

Lưu ý:
- YouTube: hạn mức mặc định 10.000 đơn vị mỗi ngày (mỗi lần tìm 100, mỗi trang bình luận 1). Khóa gửi qua tiêu đề HTTP, không nằm trong URL. Chưa có khóa thì collector dừng với mã thoát 3.
- Google Trends nghỉ tối thiểu 15 giây giữa các yêu cầu. Khoảng thời gian dưới 5 năm thì Trends trả theo tuần, collector tự gộp về tháng. Bị chặn 429 vẫn không vượt qua thì dừng, không đổi IP hay dùng proxy.
- Báo chí: Google News chỉ trả tối đa khoảng 100 tin mỗi truy vấn theo tháng; báo chí quốc tế gần như không có tin về các nền tảng này.
- Vòng `run_pipeline.py` mặc định chỉ chạy Google Play và App Store. Thêm `--with-context` thì vòng chạy cả báo chí (nạp `clean.news_article`) và YouTube (khi có `YOUTUBE_API_KEY`). Trends và thông tin ứng dụng chạy tay.
- Kiểm thử không gọi mạng: `python -m pytest src/etl/collectors/tests`.
