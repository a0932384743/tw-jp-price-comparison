"""
FastAPI router – search endpoint.

POST /api/search
  Accept: multipart/form-data  (field `query` for text OR `image` for file upload)
  Returns: SearchResponse JSON
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.db import get_session
from app.models.database import PriceCache, SearchHistory
from app.schemas.product import SearchResponse
from app.services.advisor import generate_buying_advice
from app.services.ai_agent import analyze_input
from app.services.scraper import fetch_jp_prices, fetch_tw_prices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


async def _get_cached_prices(keyword: str, market: str, session) -> list | None:
    """Return today's cached listings or None if cache is cold."""
    from sqlalchemy import select
    from app.schemas.product import PriceListing

    result = await session.execute(
        select(PriceCache).where(
            PriceCache.keyword == keyword,
            PriceCache.market == market,
            PriceCache.cache_date == date.today(),
        )
    )
    rows = result.scalars().all()
    if not rows:
        return None
    return [
        PriceListing(
            platform=r.platform,
            title=r.title,
            price=r.price,
            currency=r.currency,
            url=r.url,
        )
        for r in rows
    ]


async def _save_cache(keyword: str, market: str, listings, search_id, session) -> None:
    for listing in listings:
        session.add(
            PriceCache(
                search_id=search_id,
                keyword=keyword,
                market=market,
                platform=listing.platform,
                title=listing.title,
                price=listing.price,
                currency=listing.currency,
                url=listing.url,
                cache_date=date.today(),
            )
        )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search and compare product prices between Taiwan and Japan",
)
async def search(
    query: str | None = Form(default=None, description="Product name or description"),
    image: UploadFile | None = File(default=None, description="Product image (jpg/png/webp)"),
):
    """
    ## End-to-end search flow

    1. **AI Agent** identifies the product from text or image and returns
       optimised search keywords for both TW and JP markets.
    2. **Scrapers** fetch live (or cached) prices from momo/Shopee and Amazon
       JP/Rakuten concurrently.
    3. **AI Advisor** analyses the price data against the current exchange rate
       and Japan's 10% tax-free refund to produce a structured recommendation.
    """
    # ── Validate input ──────────────────────────────────────────────────────
    if not query and not image:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either `query` (text) or `image` (file).",
        )

    # ── Step 1: AI keyword mapping ──────────────────────────────────────────
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

    # ── Step 2: Concurrent price fetching (with DB cache) ──────────────────
    try:
        async with get_session() as session:
            cached_tw = await _get_cached_prices(mapping.refined_tw_keyword, "TW", session)
            cached_jp = await _get_cached_prices(mapping.refined_jp_keyword, "JP", session)

            if cached_tw is None or cached_jp is None:
                tw_prices, jp_prices = await asyncio.gather(
                    fetch_tw_prices(mapping.refined_tw_keyword),
                    fetch_jp_prices(mapping.refined_jp_keyword),
                )
            else:
                tw_prices = cached_tw
                jp_prices = cached_jp
                logger.info("Cache hit for TW=%s / JP=%s", mapping.refined_tw_keyword, mapping.refined_jp_keyword)

            # ── Step 3: AI buying advice ────────────────────────────────────
            advice, rate = await generate_buying_advice(tw_prices, jp_prices)

            # ── Persist search history + cache ──────────────────────────────
            history = SearchHistory(
                input_type="image" if image else "text",
                raw_query=raw_query,
                image_filename=image_filename,
                refined_tw_keyword=mapping.refined_tw_keyword,
                refined_jp_keyword=mapping.refined_jp_keyword,
                category=mapping.category,
                exchange_rate_jpy_twd=rate,
                best_deal_location=advice.best_deal_location,
                verdict=advice.verdict,
            )
            session.add(history)
            await session.flush()  # populate history.id before FK references

            if cached_tw is None:
                await _save_cache(mapping.refined_tw_keyword, "TW", tw_prices, history.id, session)
            if cached_jp is None:
                await _save_cache(mapping.refined_jp_keyword, "JP", jp_prices, history.id, session)

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
    )
