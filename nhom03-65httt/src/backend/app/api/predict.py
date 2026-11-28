"""Điểm cuối AI còn là KHUNG, trả 501 cho tới khi mô hình/LLM được tích hợp (M1 cảm xúc đã chạy thật, xem sentiment.py).

Hợp đồng (đường dẫn, dữ liệu vào) được chốt sớm để website và n8n có thể gọi thử.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["AI (khung, chưa tích hợp)"])
