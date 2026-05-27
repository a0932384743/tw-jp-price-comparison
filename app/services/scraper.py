"""
Price Scraper – Taiwan & Japan e-commerce platforms.

Architecture note
-----------------
Real scraping requires per-platform session management, proxy rotation, and
HTML parsing that is highly fragile against site redesigns.  This module
provides:

  1. A realistic *mock* layer (enabled when APP_ENV != "production") that
     returns plausible seeded data so the rest of the pipeline can be
     developed and tested without hitting live sites.

  2. A *stub* for real HTTP-based scraping using httpx + BeautifulSoup that
     you can flesh out per platform as needed.

Toggle via the APP_ENV environment variable:
  - ``development`` (default) → mock data
  - ``production``             → live HTTP requests
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from typing import Callable

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.schemas.product import PriceListing

logger = logging.getLogger(__name__)


# =========================================================================== #
# Mock data helpers
# =========================================================================== #

def _seed_from(keyword: str) -> int:
    """Deterministic seed so the same keyword always returns the same mock prices."""
    return int(hashlib.md5(keyword.encode()).hexdigest(), 16) % (2**31)


def _mock_tw_prices(keyword: str) -> list[PriceListing]:
    rng = random.Random(_seed_from(keyword))
    base = rng.randint(800, 8000)
    return [
        PriceListing(
            platform="momo購物網",
            title=f"{keyword} 【momo限定】正品保固",
            price=float(base),
            currency="TWD",
            url=f"https://www.momoshop.com.tw/search/searchShop.jsp?keyword={keyword}",
        ),
        PriceListing(
            platform="蝦皮購物 (Shopee TW)",
            title=f"{keyword} 台灣賣家 快速出貨",
            price=float(rng.randint(int(base * 0.85), int(base * 0.95))),
            currency="TWD",
            url=f"https://shopee.tw/search?keyword={keyword}",
        ),
        PriceListing(
            platform="PChome 24h",
            title=f"{keyword} PChome獨家優惠",
            price=float(rng.randint(int(base * 0.90), int(base * 1.05))),
            currency="TWD",
            url=f"https://24h.pchome.com.tw/search/?q={keyword}",
        ),
    ]


def _mock_jp_prices(keyword: str) -> list[PriceListing]:
    rng = random.Random(_seed_from(keyword) ^ 0xDEADBEEF)
    # JPY prices are roughly TWD * 4–5 for comparable goods
    base = rng.randint(4000, 35000)
    return [
        PriceListing(
            platform="Amazon Japan",
            title=f"{keyword} Amazonおすすめ 正規品",
            price=float(base),
            currency="JPY",
            url=f"https://www.amazon.co.jp/s?k={keyword}",
        ),
        PriceListing(
            platform="楽天市場 (Rakuten)",
            title=f"{keyword} 楽天最安値 送料無料",
            price=float(rng.randint(int(base * 0.88), int(base * 0.98))),
            currency="JPY",
            url=f"https://search.rakuten.co.jp/search/mall/{keyword}/",
        ),
        PriceListing(
            platform="Yahoo!ショッピング",
            title=f"{keyword} Yahoo限定セール",
            price=float(rng.randint(int(base * 0.90), int(base * 1.02))),
            currency="JPY",
            url=f"https://shopping.yahoo.co.jp/search?p={keyword}",
        ),
    ]


# =========================================================================== #
# Live scraper stubs (replace mock innards with real parsing)
# =========================================================================== #

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


async def _scrape_momo(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Scrape momo購物網 search results.  Stub – fill in CSS selectors."""
    url = f"https://www.momoshop.com.tw/search/searchShop.jsp?keyword={keyword}"
    try:
        resp = await client.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        # TODO: update selectors when integrating live scraping
        for card in soup.select(".prdListArea .listAreaInner li")[:5]:
            title_el = card.select_one(".prdName")
            price_el = card.select_one(".price b")
            link_el = card.select_one("a")
            if title_el and price_el and link_el:
                price_text = price_el.text.strip().replace(",", "")
                results.append(
                    PriceListing(
                        platform="momo購物網",
                        title=title_el.text.strip(),
                        price=float(price_text),
                        currency="TWD",
                        url="https://www.momoshop.com.tw" + link_el.get("href", ""),
                    )
                )
        return results
    except Exception as exc:
        logger.warning("momo scrape failed: %s – falling back to mock", exc)
        return _mock_tw_prices(keyword)[:1]


async def _scrape_amazon_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Scrape Amazon Japan search results.  Stub – fill in CSS selectors."""
    url = f"https://www.amazon.co.jp/s?k={keyword}"
    try:
        resp = await client.get(url, headers={**_HEADERS, "Accept-Language": "ja-JP,ja;q=0.9"}, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select('[data-component-type="s-search-result"]')[:5]:
            title_el = card.select_one("h2 span")
            price_whole = card.select_one(".a-price-whole")
            link_el = card.select_one("h2 a")
            if title_el and price_whole and link_el:
                price_text = price_whole.text.strip().replace(",", "").replace(".", "")
                results.append(
                    PriceListing(
                        platform="Amazon Japan",
                        title=title_el.text.strip(),
                        price=float(price_text),
                        currency="JPY",
                        url="https://www.amazon.co.jp" + link_el.get("href", ""),
                    )
                )
        return results
    except Exception as exc:
        logger.warning("Amazon JP scrape failed: %s – falling back to mock", exc)
        return _mock_jp_prices(keyword)[:1]


# =========================================================================== #
# Public API
# =========================================================================== #

async def fetch_tw_prices(keyword: str) -> list[PriceListing]:
    """Return Taiwan price listings for *keyword*.

    Uses mock data in non-production environments; live scraping in production.
    """
    settings = get_settings()
    if settings.app_env != "production":
        logger.debug("Using mock TW prices for '%s'", keyword)
        await asyncio.sleep(0.05)  # simulate minor latency
        return _mock_tw_prices(keyword)

    async with httpx.AsyncClient() as client:
        results = await _scrape_momo(client, keyword)
        await asyncio.sleep(settings.scraper_request_delay)
        return results


async def fetch_jp_prices(keyword: str) -> list[PriceListing]:
    """Return Japan price listings for *keyword*.

    Uses mock data in non-production environments; live scraping in production.
    """
    settings = get_settings()
    if settings.app_env != "production":
        logger.debug("Using mock JP prices for '%s'", keyword)
        await asyncio.sleep(0.05)
        return _mock_jp_prices(keyword)

    async with httpx.AsyncClient() as client:
        results = await _scrape_amazon_jp(client, keyword)
        await asyncio.sleep(settings.scraper_request_delay)
        return results
