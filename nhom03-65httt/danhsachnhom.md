# Danh Sách Nhóm Và Phân Công Nhiệm Vụ

## 1. Thông Tin Chung

- **Tên nhóm:** nhom03-65httt
- **Tên lớp học phần:** Hệ Thống Kinh Doanh Thông Minh - Lớp 65 HTTT
- **Tên đề tài:** Hệ thống phân tích trải nghiệm người học và cạnh tranh giữa các nền tảng E-learning, ứng dụng AI phân tích cảm xúc và dự báo xu hướng (EduVision BI)
- **Giảng viên hướng dẫn:** Ths. Đỗ Oanh Cường

---

## 2. Danh Sách Thành Viên

| STT | Họ và Tên | Mã Sinh Viên | Lớp Sinh Hoạt | Vai Trò | Nhiệm Vụ Phân Công | Tỷ Lệ Đóng Góp (%) | Email |
| :-: | :--- | :-: | :-: | :--- | :--- | :-: | :--- |
| 1 | Giang Thanh Tùng | 2351160563 | 65HTTT | Nhóm trưởng | Điều phối dự án, kiến trúc tổng thể; mô hình cảm xúc M1 (PhoBERT), API FastAPI, khuyến nghị và cảnh báo tự sinh, chatbot LLM, workflow n8n, Docker Compose, tích hợp và kiểm thử | 20% | 2351160563@e.tlu.edu.vn |
| 2 | Tạ Thị Ngọc Anh | 2351160503 | 65HTTT | Thành viên | Kho dữ liệu star schema và ERD, script ETL, nhật ký chất lượng dữ liệu, mô hình dự báo M3, phát hiện bất thường | 20% | 2351160503@e.tlu.edu.vn |
| 3 | Nguyễn Thái Anh | 2351160502 | 65HTTT | Thành viên | Collector các nguồn dữ liệu, thu thập sâu, lịch sử ETL, mô hình cảm xúc theo khía cạnh M2 (ABSA) | 20% | 2351160502@e.tlu.edu.vn |
| 4 | Nguyễn Hoàng Anh | 2251161939 | 65HTTT | Thành viên | Gán nhãn và LLM gán nhãn, mô hình nền TF-IDF, website, phân quyền, nhúng Superset, kiểm thử người dùng | 20% | 2251161939@e.tlu.edu.vn |
| 5 | Hoàng Hữu Hưng | 2351160525 | 65HTTT | Thành viên | Dashboard Superset, KPI, BHI, mục khuyến nghị hành động, kịch bản demo và slide | 20% | 2351160525@e.tlu.edu.vn |

> **Ghi chú:** Danh sách phân công nhiệm vụ và tỷ lệ đóng góp ở trên mới là **dự kiến**, có thể được điều chỉnh trong quá trình thực hiện đồ án.

---

## 3. Cấu Trúc Mã Nguồn Trong Thư Mục Nhóm

Mã nguồn của nhóm phải được đặt trong thư mục này theo cấu trúc khuyến nghị:

```text
<tennhom-tenlop>/
├── danhsachnhom.md        # Tệp tin thông tin nhóm này
├── README.md              # (Tùy chọn) Hướng dẫn cài đặt và chạy mã nguồn của riêng nhóm
├── docs/                  # Tài liệu phân tích, thiết kế, báo cáo đồ án
│   └── baocao.pdf
└── src/                   # Mã nguồn của dự án
    ├── backend/
    └── frontend/
```

---

## 4. Hướng Dẫn Cài Đặt Và Thực Thi Mã Nguồn

### 4.1. Môi trường yêu cầu
- Hệ điều hành: [Ví dụ: Windows 10/11, Ubuntu 22.04]
- Nền tảng thực thi: [Ví dụ: Node.js >= 18.x, Python >= 3.10, JDK >= 17]
- Cơ sở dữ liệu: [Ví dụ: PostgreSQL 15, MySQL 8.0, MongoDB 6.0]

### 4.2. Các bước cài đặt và khởi chạy
1. Bước 1: Thiết lập cấu hình môi trường (sao chép tệp cấu hình mẫu và điền tham số).
2. Bước 2: Cài đặt các gói phụ thuộc.
3. Bước 3: Khởi chạy ứng dụng.
