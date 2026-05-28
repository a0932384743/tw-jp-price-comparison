"""
Taiwan-Japan Price Comparison & AI Advisory System
Entry point – run with:  uvicorn main:app --reload
"""
from __future__ import annotations

import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting up in %s mode", settings.app_env)

    if settings.firebase_service_account_json:
        from app.core.db import init_firebase
        init_firebase(settings.firebase_service_account_json)
    else:
        logger.warning(
            "FIREBASE_SERVICE_ACCOUNT_JSON not set – search history and price cache disabled."
        )

    yield
    logger.info("Shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="台日商品比價 AI 顧問系統",
        description=(
            "Input a product name or upload an image. "
            "The system identifies the product, fetches real-time prices from Taiwan and Japan, "
            "and provides an AI-powered cross-market purchasing recommendation."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.get("/health", tags=["System"])
    async def health():
        from app.core.db import is_available
        return {
            "status": "ok",
            "env": settings.app_env,
            "firebase": is_available(),
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("main:app", host="0.0.0.0", port=settings.app_port, reload=True)
