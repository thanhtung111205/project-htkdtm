# Ảnh Docker cho API FastAPI của EduVision BI (nhóm 03).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Cài thư viện trước để tận dụng cache của Docker khi chỉ sửa mã.
COPY requirements.txt .
RUN pip install -r requirements.txt

# M1 cảm xúc (T2): torch bản CPU và thư viện mô hình. Ảnh nhẹ không có M1: docker compose build --build-arg INSTALL_M1=0 api
# (khi đó /predict/sentiment trả 503). Tệp mô hình không nằm trong ảnh, docker-compose gắn ./models vào /app/models.
ARG INSTALL_M1=1
COPY requirements-m1.txt .
RUN if [ "$INSTALL_M1" = "1" ]; then \
        pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu && \
        pip install -r requirements-m1.txt; \
    fi

COPY app ./app

# Chạy bằng người dùng thường, không dùng root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
