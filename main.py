"""
Taiwan-Japan Price Comparison & AI Advisory System
Entry point – run with:  uvicorn main:app --reload
"""
from __future__ import annotations

import logging
import time

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("═══════════════════════════════════════════════")
    logger.info("Starting up — env=%s  port=%s", settings.app_env, settings.app_port)

    # Firebase
    if settings.firebase_service_account_json:
        from app.core.db import init_firebase
        init_firebase(settings.firebase_service_account_json)
        logger.info("Firebase ✓ (project=%s)", settings.firebase_project_id)
    else:
        logger.warning("Firebase ✗ — FIREBASE_SERVICE_ACCOUNT_JSON not set (cache disabled)")

    # Optional image APIs
    logger.info(
        "Image APIs — SerpApi=%s | Google CSE=%s | Rakuten=%s | Yahoo JP=%s",
        "✓" if settings.serpapi_key        else "✗ (set SERPAPI_KEY)",
        "✓" if (settings.google_api_key and settings.google_cse_id) else "✗ (set GOOGLE_API_KEY + GOOGLE_CSE_ID)",
        "✓" if settings.rakuten_app_id     else "✗ (set RAKUTEN_APP_ID)",
        "✓" if settings.yahoo_jp_app_id    else "✗ (set YAHOO_JP_APP_ID)",
    )
    logger.info("═══════════════════════════════════════════════")

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

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - t0
        # Skip noisy health-check logs
        if request.url.path != "/health":
            logger.info(
                "%-6s %-40s → %d  (%.2fs)",
                request.method,
                request.url.path,
                response.status_code,
                duration,
            )
        return response

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
