# E1 bổ sung: có và không dùng dữ liệu UIT-VSFC (G11)

Đề cương mục 4.3 và 8.1 yêu cầu dùng UIT-VSFC và các bộ cảm xúc tiếng Việt khác để kiểm tra khả năng tổng quát hóa của M1.
Script: `src/ml/sentiment/exp_uit_vsfc.py`. Kết quả đầy đủ: `data/ml/e1_uit_vsfc.json` (ngoài Git). Chạy ngày 27/11/2026.

## Thiết lập

- **Mô hình:** TF-IDF + Logistic Regression (mô hình nền M1, `train_baseline.build_pipeline`).
  - Tham số C chọn trên tập validation của nhóm, vì mục tiêu là đánh giá ứng dụng.
  - **PhoBERT chưa chạy lại.** Với dữ liệu gấp khoảng 4 lần, việc huấn luyện mất khoảng 3 giờ trên CPU, nên kết luận dưới đây chỉ áp dụng cho mô hình nền.
- **UIT-VSFC:** 16.175 câu phản hồi của sinh viên về môn học (train 11.426, validation 1.583, test 3.166).
  - Nhãn 0, 1, 2 khớp với thứ tự tiêu cực, trung tính, tích cực của nhóm.
  - Lớp trung tính chỉ chiếm 4%.
- **Bốn cấu hình huấn luyện:**

  | Cấu hình | Dữ liệu huấn luyện | Số câu |
  |---|---|---:|
  | A | chỉ dữ liệu của nhóm (nhãn LLM; đây là M1 nền hiện tại) | 3.020 |
  | B | dữ liệu nhóm + toàn bộ UIT-VSFC train | 14.446 |
  | B2 | dữ liệu nhóm + mẫu UIT-VSFC cùng cỡ (hạt 42) | 6.040 |
  | C | chỉ UIT-VSFC train | 11.426 |

- **Tập đo:**
  - test của nhóm: 378 câu, nhãn LLM;
  - tập vàng người gán: 1.144 câu, nhãn hai người đồng ý;
  - tập vàng LLM: 1.169 câu;
  - test UIT-VSFC: 3.166 câu, khác miền với dữ liệu của nhóm.

## Kết quả (macro-F1; trong ngoặc là F1 lớp trung tính)

| Cấu hình | Test nhóm | **Vàng người** | Vàng LLM | Test UIT-VSFC |
|---|---:|---:|---:|---:|
| A. Chỉ nhóm | **0,788** (0,659) | **0,659** (0,396) | **0,791** (0,604) | 0,528 (0,151) |
| B. Nhóm + toàn bộ UIT | 0,722 (0,560) | 0,632 (0,373) | 0,731 (0,504) | 0,729 (0,378) |
| B2. Nhóm + UIT cùng cỡ | 0,746 (0,582) | 0,655 (0,380) | 0,786 (0,592) | 0,674 (0,251) |
| C. Chỉ UIT | 0,575 (0,291) | 0,527 (0,202) | 0,587 (0,250) | **0,744** (0,418) |

## Kết luận

1. **Thêm UIT-VSFC không cải thiện M1 trên đánh giá ứng dụng.**
   - Trên tập vàng người gán, macro-F1 giảm từ 0,659 xuống 0,632 khi thêm toàn bộ UIT-VSFC, và xuống 0,655 khi chỉ thêm mẫu cùng cỡ.
   - Lớp trung tính cũng giảm.
   - Nguyên nhân là UIT-VSFC khác miền (phản hồi về giảng dạy, câu ngắn, đã tách từ) và gần như không có câu trung tính.
2. **Mô hình chỉ học dữ liệu của nhóm tổng quát hóa kém sang miền khác:** macro-F1 trên test UIT-VSFC chỉ 0,528. Đây là hạn chế cần ghi rõ.
   - Thêm UIT-VSFC giúp miền đó lên 0,674–0,729 nhưng làm giảm miền chính của dự án.
3. **Quyết định:** M1 dùng trong hệ thống giữ cấu hình A, không trộn UIT-VSFC.
   - UIT-VSFC được dùng làm **tập kiểm tra tổng quát hóa ngoài miền**, đúng như mục 4.3 của đề cương.
4. **Hướng tiếp theo (chưa làm):**
   - tinh chỉnh PhoBERT theo cấu hình B2 để xem mô hình lớn có tận dụng được dữ liệu bổ trợ hay không;
   - hoặc huấn luyện hai giai đoạn: học UIT-VSFC trước, rồi tinh chỉnh bằng dữ liệu của nhóm.
