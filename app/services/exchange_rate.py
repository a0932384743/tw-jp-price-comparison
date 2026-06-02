"""
Live JPY → TWD exchange rate fetched from open.er-api.com (free, no key).

Results are cached in-memory for 1 hour to avoid hammering the API on
every search request. Falls back to the configured default if the fetch
fails or times out.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_RATE_URL = "https://open.er-api.com/v6/latest/JPY"
_CACHE_TTL = timedelta(hours=1)

_cached_rate: float | None = None
_cached_at: datetime | None = None


async def get_jpy_to_twd_rate() -> float:
    """Return the current JPY→TWD exchange rate.

    Fetches from open.er-api.com and caches for 1 hour.
    Falls back to the value in settings if the API is unavailable.
    """
    global _cached_rate, _cached_at

    now = datetime.utcnow()
    if _cached_rate is not None and _cached_at is not None:
        if now - _cached_at < _CACHE_TTL:
            logger.debug("Exchange rate cache hit: %.5f JPY/TWD", _cached_rate)
            return _cached_rate

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(_RATE_URL)
            resp.raise_for_status()
            data = resp.json()

        rate = float(data["rates"]["TWD"])
        _cached_rate = rate
        _cached_at = now
        logger.info("Live exchange rate fetched: 1 JPY = %.5f TWD", rate)
        return rate

    except Exception as exc:
        fallback = get_settings().jpy_to_twd_rate
        logger.warning(
            "Failed to fetch live exchange rate (%s), using fallback %.4f", exc, fallback
        )
        return fallback
