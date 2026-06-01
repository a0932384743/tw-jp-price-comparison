"""
FastAPI router – search endpoint.

POST /api/search
  Accept: multipart/form-data  (field `query` for text OR `image` for file upload)
  Returns: SearchResponse JSON
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from firebase_admin import firestore as fs
from tenacity import RetryError

from app.core.db import get_db, is_available
from app.schemas.product import PriceListing, SearchResponse
from app.services.advisor import generate_buying_advice
from app.services.ai_agent import analyze_input
from app.services.exchange_rate import get_jpy_to_twd_rate
from app.services.scraper import fetch_jp_prices, fetch_product_thumbnail, fetch_tw_prices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ── Firestore helpers ────────────────────────────────────────────────────────

def _cache_doc_id(keyword: str, market: str) -> str:
    """Stable Firestore document ID for a (keyword, market, date) triple."""
    raw = f"{keyword}|{market}|{date.today()}"
    return hashlib.md5(raw.encode()).hexdigest()


async def _get_cached_prices(keyword: str, market: str) -> list[PriceListing] | None:
    if not is_available():
        return None

    cache_id = _cache_doc_id(keyword, market)

    def _query():
        doc = get_db().collection("price_cache").document(cache_id).get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("cache_date") == str(date.today()):
                return data.get("listings", [])
        return None

    raw = await asyncio.to_thread(_query)
    if raw is None:
        return None
    return [PriceListing(**item) for item in raw]


async def _persist(
    *,
    input_type: str,
    raw_query: str | None,
    image_filename: str | None,
    mapping,
    rate: float,
    advice,
    tw_prices: list[PriceListing],
    jp_prices: list[PriceListing],
    tw_was_cached: bool,
    jp_was_cached: bool,
) -> None:
    if not is_available():
        return

    def _write():
        db = get_db()

        # search_history document
        search_ref = db.collection("search_history").document()
        search_ref.set({
            "created_at": fs.SERVER_TIMESTAMP,
            "input_type": input_type,
            "raw_query": raw_query,
            "image_filename": image_filename,
            "refined_tw_keyword": mapping.refined_tw_keyword,
            "refined_jp_keyword": mapping.refined_jp_keyword,
            "category": mapping.category,
            "exchange_rate_jpy_twd": rate,
            "best_deal_location": advice.best_deal_location,
            "verdict": advice.verdict,
        })

        # price_cache – only write if we fetched fresh data
        if not tw_was_cached:
            tw_id = _cache_doc_id(mapping.refined_tw_keyword, "TW")
            db.collection("price_cache").document(tw_id).set({
                "keyword": mapping.refined_tw_keyword,
                "market": "TW",
                "cache_date": str(date.today()),
                "search_id": search_ref.id,
                "listings": [l.model_dump() for l in tw_prices],
            })

        if not jp_was_cached:
            jp_id = _cache_doc_id(mapping.refined_jp_keyword, "JP")
            db.collection("price_cache").document(jp_id).set({
                "keyword": mapping.refined_jp_keyword,
                "market": "JP",
                "cache_date": str(date.today()),
                "search_id": search_ref.id,
                "listings": [l.model_dump() for l in jp_prices],
            })

    await asyncio.to_thread(_write)


# ── Search endpoint ──────────────────────────────────────────────────────────

@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search and compare product prices between Taiwan and Japan",
)
async def search(
    query: str | None = Form(default=None, description="Product name or description"),
    image: UploadFile | None = File(default=None, description="Product image (jpg/png/webp)"),
):
    if not query and not image:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either `query` (text) or `image` (file).",
        )

    # ── Step 1: AI keyword mapping ──────────────────────────────────────────
    try:
        if image:
            image_bytes = await image.read()
            media_type = image.content_type or "image/jpeg"
            mapping = await analyze_input("image", image_bytes, media_type=media_type)
            raw_query = None
            image_filename = image.filename
        else:
            mapping = await analyze_input("text", query)
            raw_query = query
            image_filename = None
    except RetryError as e:
        last_exc = e.last_attempt.exception()
        raise HTTPException(status_code=429, detail=f"AI服務暫時無法使用: {last_exc}")
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))

    # ── Step 2: Live exchange rate + price fetching (with Firestore cache) ──
    try:
        live_rate, cached_tw, cached_jp = await asyncio.gather(
            get_jpy_to_twd_rate(),
            _get_cached_prices(mapping.refined_tw_keyword, "TW"),
            _get_cached_prices(mapping.refined_jp_keyword, "JP"),
        )

        tw_was_cached = cached_tw is not None
        jp_was_cached = cached_jp is not None

        if tw_was_cached and jp_was_cached:
            tw_prices, jp_prices = cached_tw, cached_jp
            logger.info("Firestore cache hit: TW=%s / JP=%s",
                        mapping.refined_tw_keyword, mapping.refined_jp_keyword)
            product_image_url = await fetch_product_thumbnail(mapping.refined_tw_keyword)
        else:
            tw_prices, jp_prices, product_image_url = await asyncio.gather(
                fetch_tw_prices(mapping.refined_tw_keyword),
                fetch_jp_prices(mapping.refined_jp_keyword),
                fetch_product_thumbnail(mapping.refined_tw_keyword),
            )

        # ── Step 3: AI buying advice ────────────────────────────────────────
        advice, rate = await generate_buying_advice(
            tw_prices, jp_prices, current_exchange_rate=live_rate
        )

        # ── Step 4: Persist to Firestore (fire-and-forget) ──────────────────
        asyncio.create_task(_persist(
            input_type="image" if image else "text",
            raw_query=raw_query,
            image_filename=image_filename,
            mapping=mapping,
            rate=rate,
            advice=advice,
            tw_prices=tw_prices,
            jp_prices=jp_prices,
            tw_was_cached=tw_was_cached,
            jp_was_cached=jp_was_cached,
        ))

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {exc}",
        )

    return SearchResponse(
        keyword_mapping=mapping,
        tw_listings=tw_prices,
        jp_listings=jp_prices,
        exchange_rate_jpy_twd=rate,
        advice=advice,
        product_image_url=product_image_url,
    )
