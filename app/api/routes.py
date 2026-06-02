"""
FastAPI router – search endpoint.

POST /api/search
  Accept: multipart/form-data  (field `query` for text OR `image` for file upload)
  Returns: SearchResponse JSON

GET /api/thumbnail?url={url}
  Proxy a website screenshot via mshots (server-side fetch → CORS-safe response).
  Returns: image/jpeg or image/png with Cache-Control + CORS headers.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from firebase_admin import firestore as fs
from tenacity import RetryError

import httpx

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


# ── Thumbnail proxy ──────────────────────────────────────────────────────────
# key → (bytes, content_type, expires_at)
_thumb_cache: dict[str, tuple[bytes, str, float]] = {}
_THUMB_TTL = 86_400  # 24 h
_UA_THUMB = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@router.get(
    "/thumbnail",
    summary="Server-side website screenshot proxy",
    response_description="JPEG/PNG screenshot of the given URL",
)
async def thumbnail_proxy(url: str = Query(..., description="Website URL to screenshot")):
    """Fetch a website screenshot via mshots on the server side and return it
    with proper CORS headers.  This avoids any browser-side CORS or
    service-restriction issues the frontend would encounter when loading
    third-party screenshot URLs directly.

    Results are cached in memory for 24 hours.
    """
    cache_key = hashlib.md5(url.encode()).hexdigest()

    # ── cache hit ────────────────────────────────────────────────────────────
    cached = _thumb_cache.get(cache_key)
    if cached:
        data, ct, expires = cached
        if time.time() < expires:
            return Response(
                content=data, media_type=ct,
                headers={"Cache-Control": f"max-age={_THUMB_TTL}", "Access-Control-Allow-Origin": "*"},
            )

    # ── fetch from mshots ────────────────────────────────────────────────────
    # mshots returns a placeholder on the first hit (screenshot is generated
    # async).  We try up to 3 times with a short sleep to get the real image.
    mshots = f"https://s0.wordpress.com/mshots/v1/{quote(url, safe='')}?w=280&h=280"
    data, ct = None, "image/jpeg"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for attempt in range(3):
                resp = await client.get(mshots, headers={"User-Agent": _UA_THUMB}, timeout=20)
                if resp.status_code == 200 and resp.content:
                    ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                    # mshots placeholder is tiny (<3 KB); real screenshot is larger
                    if len(resp.content) >= 3_000:
                        data = resp.content
                        break
                if attempt < 2:
                    await asyncio.sleep(3)   # wait for mshots to generate
    except Exception as exc:
        logger.warning("thumbnail_proxy mshots failed for '%s': %s", url, exc)

    if not data:
        raise HTTPException(status_code=503, detail="Screenshot not yet available; retry in a few seconds")

    _thumb_cache[cache_key] = (data, ct, time.time() + _THUMB_TTL)
    return Response(
        content=data, media_type=ct,
        headers={"Cache-Control": f"max-age={_THUMB_TTL}", "Access-Control-Allow-Origin": "*"},
    )
