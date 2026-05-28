"""
Price Scraper – Taiwan & Japan e-commerce platforms.

Production runs concurrent real HTTP scrapers:
  Taiwan:  PChome 24h (JSON API, no auth) + momo購物網 (HTML)
  Japan:   楽天市場 (HTML) + Yahoo!ショッピング (HTML)

Development uses deterministic mock data so the pipeline works
without hitting live sites (toggle via APP_ENV).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.schemas.product import PriceListing

logger = logging.getLogger(__name__)

# ── Request headers ─────────────────────────────────────────────────────────

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS_TW = {"User-Agent": _UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
_HEADERS_JP = {"User-Agent": _UA, "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8"}

# ── Price outlier filter ─────────────────────────────────────────────────────

def _filter_outliers(listings: list[PriceListing], min_ratio: float = 0.35) -> list[PriceListing]:
    """Remove listings whose price is far below the group median.

    Accessories and unrelated products tend to be much cheaper than the
    actual searched item. Keeping only items >= median * min_ratio removes
    the most obvious outliers while preserving genuine price variation.
    """
    if len(listings) <= 1:
        return listings
    prices = sorted(l.price for l in listings)
    median = prices[len(prices) // 2]
    return [l for l in listings if l.price >= median * min_ratio]


# ── Mock helpers (development only) ─────────────────────────────────────────

def _seed_from(keyword: str) -> int:
    return int(hashlib.md5(keyword.encode()).hexdigest(), 16) % (2 ** 31)


def _mock_tw_prices(keyword: str) -> list[PriceListing]:
    rng = random.Random(_seed_from(keyword))
    base = rng.randint(800, 8000)
    kw = quote(keyword)
    return [
        PriceListing(platform="momo購物網", title=f"{keyword} 【momo限定】正品保固",
                     price=float(base), currency="TWD",
                     url=f"https://www.momoshop.com.tw/search/searchShop.jsp?keyword={kw}"),
        PriceListing(platform="蝦皮購物 (Shopee TW)", title=f"{keyword} 台灣賣家 快速出貨",
                     price=float(rng.randint(int(base * 0.85), int(base * 0.95))), currency="TWD",
                     url=f"https://shopee.tw/search?keyword={kw}"),
        PriceListing(platform="PChome 24h", title=f"{keyword} PChome獨家優惠",
                     price=float(rng.randint(int(base * 0.90), int(base * 1.05))), currency="TWD",
                     url=f"https://24h.pchome.com.tw/search/?q={kw}"),
    ]


def _mock_jp_prices(keyword: str) -> list[PriceListing]:
    rng = random.Random(_seed_from(keyword) ^ 0xDEADBEEF)
    base = rng.randint(4000, 35000)
    kw = quote(keyword)
    return [
        PriceListing(platform="楽天市場", title=f"{keyword} 楽天最安値 送料無料",
                     price=float(base), currency="JPY",
                     url=f"https://search.rakuten.co.jp/search/mall/{kw}/"),
        PriceListing(platform="Yahoo!ショッピング", title=f"{keyword} Yahoo限定セール",
                     price=float(rng.randint(int(base * 0.90), int(base * 1.02))), currency="JPY",
                     url=f"https://shopping.yahoo.co.jp/search?p={kw}"),
        PriceListing(platform="Amazon Japan", title=f"{keyword} Amazon正規品",
                     price=float(rng.randint(int(base * 0.88), int(base * 0.98))), currency="JPY",
                     url=f"https://www.amazon.co.jp/s?k={kw}"),
    ]


# ── Taiwan live scrapers ─────────────────────────────────────────────────────

async def _scrape_pchome(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """PChome 24h JSON search API – no authentication required."""
    url = (
        f"https://ecshweb.pchome.com.tw/search/v3.3/all/results"
        f"?q={quote(keyword)}&page=1&sort=rnk/dc"
    )
    try:
        resp = await client.get(url, headers=_HEADERS_TW, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for prod in data.get("Prods", [])[:8]:
            name = prod.get("Name", "").strip()
            price = prod.get("Price", {}).get("P") or prod.get("Price", {}).get("M")
            prod_id = prod.get("Id", "")
            if name and price:
                results.append(PriceListing(
                    platform="PChome 24h",
                    title=name,
                    price=float(price),
                    currency="TWD",
                    url=f"https://24h.pchome.com.tw/prod/{prod_id}",
                ))
        results = _filter_outliers(results)[:5]
        logger.info("PChome: %d results for '%s'", len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("PChome scrape failed for '%s': %s", keyword, exc)
        return []


async def _scrape_momo(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """momo購物網 HTML search."""
    url = (
        f"https://www.momoshop.com.tw/search/searchShop.jsp"
        f"?keyword={quote(keyword)}&searchType=1&cateLevel=0&ent=k&userIN={quote(keyword)}"
    )
    try:
        resp = await client.get(url, headers=_HEADERS_TW, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select("li.goodsItem")[:8]:
            title_el = card.select_one(".prdName")
            price_el = card.select_one(".price b")
            link_el = card.select_one("a")
            if not (title_el and price_el):
                continue
            try:
                price = float(price_el.text.strip().replace(",", ""))
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.momoshop.com.tw{href}"
                results.append(PriceListing(
                    platform="momo購物網",
                    title=title_el.text.strip(),
                    price=price,
                    currency="TWD",
                    url=full_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:5]
        logger.info("momo: %d results for '%s'", len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("momo scrape failed for '%s': %s", keyword, exc)
        return []


# ── Japan live scrapers ──────────────────────────────────────────────────────

async def _scrape_rakuten_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """楽天市場 HTML search."""
    url = f"https://search.rakuten.co.jp/search/mall/{quote(keyword)}/"
    try:
        resp = await client.get(url, headers=_HEADERS_JP, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select("div.searchresultitem")[:8]:
            title_el = (
                card.select_one(".content.title a")
                or card.select_one("a.title")
                or card.select_one("h2 a")
            )
            price_el = (
                card.select_one(".price_wrap .important")
                or card.select_one(".content.price .important")
                or card.select_one(".important")
            )
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                results.append(PriceListing(
                    platform="楽天市場",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="JPY",
                    url=title_el.get("href", ""),
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:5]
        logger.info("Rakuten: %d results for '%s'", len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("Rakuten scrape failed for '%s': %s", keyword, exc)
        return []


async def _scrape_yahoo_shopping_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Yahoo!ショッピング – try __NEXT_DATA__ JSON first, then HTML fallback."""
    url = f"https://shopping.yahoo.co.jp/search?p={quote(keyword)}&sort=-score"
    try:
        resp = await client.get(url, headers=_HEADERS_JP, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []

        # ── Attempt 1: parse embedded Next.js JSON ───────────────────────
        next_script = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_script and next_script.string:
            try:
                next_data = json.loads(next_script.string)
                # Walk common paths to find item list
                items = (
                    next_data.get("props", {}).get("pageProps", {})
                    .get("initialState", {}).get("search", {}).get("result", {})
                    .get("items", [])
                )
                if not items:
                    items = (
                        next_data.get("props", {}).get("pageProps", {})
                        .get("search", {}).get("items", [])
                    )
                for item in items[:5]:
                    name = item.get("name") or item.get("title") or ""
                    price = item.get("price") or item.get("lowestPrice") or 0
                    item_url = item.get("url") or item.get("productUrl") or ""
                    if name and price:
                        results.append(PriceListing(
                            platform="Yahoo!ショッピング",
                            title=str(name).strip(),
                            price=float(price),
                            currency="JPY",
                            url=str(item_url),
                        ))
                if results:
                    logger.info("Yahoo Shopping (JSON): %d results for '%s'", len(results), keyword)
                    return results
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass

        # ── Attempt 2: HTML selectors fallback ───────────────────────────
        # Yahoo Shopping obfuscates class names with CSS modules; try broad attribute selectors
        for card in soup.select("li[class*='SearchResult'], li[class*='Item'], li[class*='item']")[:5]:
            title_el = (
                card.select_one("a[class*='Title']")
                or card.select_one("a[class*='title']")
                or card.select_one("h3 a, h2 a")
            )
            price_el = (
                card.select_one("[class*='Price'] span")
                or card.select_one("[class*='price'] span")
            )
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                href = title_el.get("href", "")
                results.append(PriceListing(
                    platform="Yahoo!ショッピング",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="JPY",
                    url=href if href.startswith("http") else f"https://shopping.yahoo.co.jp{href}",
                ))
            except (ValueError, AttributeError):
                continue

        logger.info("Yahoo Shopping (HTML): %d results for '%s'", len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("Yahoo Shopping JP scrape failed for '%s': %s", keyword, exc)
        return []


# ── Gemini Search fallback (used when all scrapers return 0 results) ─────────

async def _fallback_prices_via_gemini(keyword: str, market: str) -> list[PriceListing]:
    """Use Gemini + Google Search grounding to find live prices when scrapers fail.

    First tries grounded search (real-time Google results).
    Falls back to Gemini AI knowledge if grounding is unavailable.
    """
    from app.services.gemini_client import generate_with_fallback, search_with_grounding

    settings = get_settings()

    if market == "TW":
        prompt = (
            f'Search Google Shopping for the current retail price of "{keyword}" '
            f"in Taiwan (台灣). Look at results from PChome 24h, momo購物網, "
            f"Yahoo購物中心, and Shopee台灣.\n\n"
            f"Return ONLY a valid JSON array (no markdown, no explanation):\n"
            f'[{{"platform":"PChome 24h","title":"full product name","price":9490,'
            f'"currency":"TWD","url":"https://24h.pchome.com.tw/..."}}]\n\n'
            f"Include 3-5 results with real current market prices in TWD."
        )
        currency = "TWD"
    else:
        prompt = (
            f'Search Google Shopping for the current retail price of "{keyword}" '
            f"in Japan (日本). Look at results from 楽天市場, Yahoo!ショッピング, "
            f"Amazon.co.jp, and ヨドバシカメラ.\n\n"
            f"Return ONLY a valid JSON array (no markdown, no explanation):\n"
            f'[{{"platform":"楽天市場","title":"full product name","price":37980,'
            f'"currency":"JPY","url":"https://search.rakuten.co.jp/..."}}]\n\n'
            f"Include 3-5 results with real current market prices in JPY."
        )
        currency = "JPY"

    # Try grounded search first (live Google results)
    text = await search_with_grounding(settings.gemini_api_key, prompt)

    # Fall back to AI knowledge if grounding unavailable
    if not text:
        logger.info("Grounding unavailable, using Gemini AI knowledge for '%s' (%s)", keyword, market)
        try:
            response, _ = await generate_with_fallback(
                api_key=settings.gemini_api_key,
                contents=prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": 1024},
            )
            text = response.text
        except Exception as exc:
            logger.warning("Gemini AI price fallback also failed for '%s': %s", keyword, exc)
            return []

    # Parse JSON from response text
    try:
        clean = text.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        start, end = clean.find("["), clean.rfind("]") + 1
        if start < 0 or end <= start:
            raise ValueError("No JSON array found in response")
        items = json.loads(clean[start:end])
        results = []
        for item in items:
            price = float(item.get("price", 0))
            title = str(item.get("title", "")).strip()
            if price > 0 and title:
                results.append(PriceListing(
                    platform=str(item.get("platform", "電商平台")),
                    title=title,
                    price=price,
                    currency=str(item.get("currency", currency)),
                    url=str(item.get("url", "")),
                ))
        logger.info("Gemini fallback (%s): %d results for '%s'", market, len(results), keyword)
        return results
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse Gemini price response for '%s': %s | text: %.200s", keyword, exc, text)
        return []


# ── Public API ───────────────────────────────────────────────────────────────

async def fetch_tw_prices(keyword: str) -> list[PriceListing]:
    """Return Taiwan listings – PChome API + momo, with Gemini fallback."""
    settings = get_settings()
    if settings.app_env != "production":
        logger.debug("DEV mock TW prices for '%s'", keyword)
        await asyncio.sleep(0.05)
        return _mock_tw_prices(keyword)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        pchome_results, momo_results = await asyncio.gather(
            _scrape_pchome(client, keyword),
            _scrape_momo(client, keyword),
        )
    combined = pchome_results + momo_results
    await asyncio.sleep(settings.scraper_request_delay)

    if not combined:
        logger.warning("All TW scrapers failed for '%s', falling back to Gemini Search", keyword)
        combined = await _fallback_prices_via_gemini(keyword, "TW")

    logger.info("TW total: %d listings for '%s'", len(combined), keyword)
    return combined


async def fetch_jp_prices(keyword: str) -> list[PriceListing]:
    """Return Japan listings – Rakuten + Yahoo Shopping, with Gemini fallback."""
    settings = get_settings()
    if settings.app_env != "production":
        logger.debug("DEV mock JP prices for '%s'", keyword)
        await asyncio.sleep(0.05)
        return _mock_jp_prices(keyword)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        rakuten_results, yahoo_results = await asyncio.gather(
            _scrape_rakuten_jp(client, keyword),
            _scrape_yahoo_shopping_jp(client, keyword),
        )
    combined = rakuten_results + yahoo_results
    await asyncio.sleep(settings.scraper_request_delay)

    if not combined:
        logger.warning("All JP scrapers failed for '%s', falling back to Gemini Search", keyword)
        combined = await _fallback_prices_via_gemini(keyword, "JP")

    logger.info("JP total: %d listings for '%s'", len(combined), keyword)
    return combined
