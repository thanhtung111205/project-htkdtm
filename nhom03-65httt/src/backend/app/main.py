"""Điểm vào của API FastAPI (EduVision BI, nhóm 03)."""

import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import anomaly, auth, chat, forecast, health, kpi, platforms, predict, reviews, sentiment
from app.core.config import get_settings
from app.services import sentiment as sentiment_service


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="EduVision BI API",
        description="API phục vụ website, n8n và Superset. M1 cảm xúc và chatbot tầng 1 chạy thật; M2 còn là khung (trả 501).",
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
    app.include_router(auth.router)
    app.include_router(reviews.router)
    app.include_router(forecast.router)
    app.include_router(anomaly.router)
    app.include_router(sentiment.router)
    app.include_router(chat.router)
    app.include_router(kpi.router)

    @app.on_event("startup")
    def warm_up_m1() -> None:
        if settings.m1_warmup:
            threading.Thread(target=sentiment_service.warm_up, daemon=True).start()

    return app


app = create_app()
