"""Điểm vào của API FastAPI (EduVision BI, nhóm 03)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import aspects, auth, health, platforms, predict, reviews
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EduVision BI API",
        description="API phục vụ website, n8n và Superset. Cảm xúc khía cạnh hiện dùng baseline từ khóa; mô hình M1 và dự báo chưa được nạp.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(platforms.router)
    app.include_router(predict.router)
    app.include_router(aspects.router)
    app.include_router(auth.router)
    app.include_router(reviews.router)
    return app


app = create_app()
