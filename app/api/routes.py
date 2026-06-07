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
from datetime import date, datetime, timedelta, timezone
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
from app.services.scraper import enrich_listing_images, fetch_jp_prices, fetch_product_thumbnail, fetch_tw_prices

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


async def _prefetch_mshots(listings: list[PriceListing]) -> None:
    """Fire mshots requests for each listing URL so that by the time the
    frontend calls /api/thumbnail the screenshot is already cached."""
    urls = [l.url for l in listings if l.url]
    if not urls:
        return
    mshots_headers = {"User-Agent": _UA_THUMB}
    async with httpx.AsyncClient(follow_redirects=False) as client:
        await asyncio.gather(
            *[
                client.get(
                    f"https://s0.wordpress.com/mshots/v1/{quote(u, safe='')}?w=280&h=280",
                    headers=mshots_headers,
                    timeout=10,
                )
                for u in urls
            ],
            return_exceptions=True,
        )
    logger.info("mshots prefetch done for %d URLs", len(urls))


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

    input_label = f"image:{image.filename}" if image else f"text:{query!r}"
    logger.info("▶ Search start — %s", input_label)
    pipeline_start = time.perf_counter()

    # ── Step 1: AI keyword mapping ──────────────────────────────────────────
    t0 = time.perf_counter()
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
    logger.info(
        "  [1/4] AI keyword mapping      %.2fs → TW=%s | JP=%s | category=%s",
        time.perf_counter() - t0,
        mapping.refined_tw_keyword,
        mapping.refined_jp_keyword,
        mapping.category,
    )

    # ── Step 2: Live exchange rate + price fetching (with Firestore cache) ──
    t0 = time.perf_counter()
    try:
        live_rate, cached_tw, cached_jp = await asyncio.gather(
            get_jpy_to_twd_rate(),
            _get_cached_prices(mapping.refined_tw_keyword, "TW"),
            _get_cached_prices(mapping.refined_jp_keyword, "JP"),
        )

        tw_was_cached = cached_tw is not None
        jp_was_cached = cached_jp is not None

        brand_platforms = mapping.brand_platforms or []
        if tw_was_cached and jp_was_cached:
            tw_prices, jp_prices = cached_tw, cached_jp
            product_image_url = await fetch_product_thumbnail(mapping.refined_tw_keyword)
            logger.info(
                "  [2/4] Price fetch (Firestore cache hit) %.2fs → TW=%d | JP=%d | rate=%.4f",
                time.perf_counter() - t0,
                len(tw_prices), len(jp_prices), live_rate,
            )
        else:
            tw_prices, jp_prices, product_image_url = await asyncio.gather(
                fetch_tw_prices(mapping.refined_tw_keyword, brand_platforms=brand_platforms),
                fetch_jp_prices(mapping.refined_jp_keyword, brand_platforms=brand_platforms),
                fetch_product_thumbnail(mapping.refined_tw_keyword),
            )
            logger.info(
                "  [2/4] Price fetch (live scrape)         %.2fs → TW=%d | JP=%d | rate=%.4f | img=%s",
                time.perf_counter() - t0,
                len(tw_prices), len(jp_prices), live_rate,
                "✓" if product_image_url else "✗",
            )

        # If the dedicated thumbnail fetch came up empty, reuse the best API listing image.
        if not product_image_url:
            product_image_url = next(
                (l.image_url for l in tw_prices + jp_prices if l.image_url), None
            )
            if product_image_url:
                logger.info("  product_image_url → fallback from listing image")

        # ── Step 3: Enrich missing listing images ───────────────────────────
        t0 = time.perf_counter()
        tw_missing = sum(1 for l in tw_prices if not l.image_url)
        jp_missing = sum(1 for l in jp_prices if not l.image_url)
        await asyncio.gather(
            enrich_listing_images(tw_prices, max_lookup=2),
            enrich_listing_images(jp_prices, max_lookup=2),
        )
        tw_filled = tw_missing - sum(1 for l in tw_prices if not l.image_url)
        jp_filled = jp_missing - sum(1 for l in jp_prices if not l.image_url)
        logger.info(
            "  [3/4] Image enrichment                  %.2fs → filled TW=%d/%d | JP=%d/%d",
            time.perf_counter() - t0,
            tw_filled, tw_missing, jp_filled, jp_missing,
        )

        # ── Step 4: AI buying advice ────────────────────────────────────────
        t0 = time.perf_counter()
        advice, rate = await generate_buying_advice(
            tw_prices, jp_prices, current_exchange_rate=live_rate
        )
        logger.info(
            "  [4/4] Buying advice                     %.2fs → best_deal=%s",
            time.perf_counter() - t0,
            advice.best_deal_location,
        )

        # ── Fire-and-forget tasks ────────────────────────────────────────────
        asyncio.create_task(_prefetch_mshots(tw_prices[:4] + jp_prices[:4]))
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

    total = time.perf_counter() - pipeline_start
    logger.info(
        "◀ Search done  %.2fs — TW=%d listings | JP=%d listings | deal=%s",
        total, len(tw_prices), len(jp_prices), advice.best_deal_location,
    )

    return SearchResponse(
        keyword_mapping=mapping,
        tw_listings=tw_prices,
        jp_listings=jp_prices,
        exchange_rate_jpy_twd=rate,
        advice=advice,
        product_image_url=product_image_url,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Price history endpoint ───────────────────────────────────────────────────

@router.get("/price-history", summary="Historical average prices from Firestore cache")
async def price_history_endpoint(
    keyword: str = Query(..., description="Product keyword"),
    market: str = Query(default="TW", description="TW or JP"),
):
    """Return up to 7 days of price history from the Firestore price_cache collection.

    Computes MD5 document IDs for the past 7 days and reads them in parallel.
    Returns an empty list when Firestore is unavailable.
    """
    if not is_available():
        return []

    def _fetch() -> list[dict]:
        db = get_db()
        today = date.today()
        history: list[dict] = []
        for i in range(7):
            d = today - timedelta(days=i)
            raw = f"{keyword}|{market}|{d}"
            cache_id = hashlib.md5(raw.encode()).hexdigest()
            doc = db.collection("price_cache").document(cache_id).get()
            if doc.exists:
                data = doc.to_dict()
                listings = data.get("listings", [])
                prices = [float(l.get("price", 0)) for l in listings if l.get("price", 0) > 0]
                if prices:
                    history.append({
                        "date": str(d),
                        "avg_price": round(sum(prices) / len(prices)),
                        "min_price": min(prices),
                        "count": len(prices),
                    })
        return sorted(history, key=lambda x: x["date"])

    return await asyncio.to_thread(_fetch)


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
    """Return a mshots website screenshot with CORS headers.

    Uses follow_redirects=False: mshots returns 302 while still generating the
    screenshot (and would redirect to a "Generating Preview" placeholder).
    We treat 302 as "not ready" and return 503 so the frontend falls back to
    the icon placeholder.  On subsequent requests the cached screenshot is
    returned immediately as 200.
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

    # ── fetch from mshots (no redirect following) ────────────────────────────
    # 302 = screenshot still generating → return 503, frontend shows icon.
    # 200 = screenshot ready → cache and return.
    mshots = f"https://s0.wordpress.com/mshots/v1/{quote(url, safe='')}?w=280&h=280"
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.get(mshots, headers={"User-Agent": _UA_THUMB}, timeout=15)
    except Exception as exc:
        logger.warning("thumbnail_proxy request failed for '%s': %s", url, exc)
        raise HTTPException(status_code=503, detail="Screenshot service unreachable")

    if resp.status_code in (301, 302, 307, 308):
        # mshots is still rendering – tell the frontend to use the icon instead
        raise HTTPException(status_code=503, detail="Screenshot generating, retry later")

    if resp.status_code == 200 and resp.content:
        ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        _thumb_cache[cache_key] = (resp.content, ct, time.time() + _THUMB_TTL)
        return Response(
            content=resp.content, media_type=ct,
            headers={"Cache-Control": f"max-age={_THUMB_TTL}", "Access-Control-Allow-Origin": "*"},
        )

    raise HTTPException(status_code=503, detail="Screenshot unavailable")
