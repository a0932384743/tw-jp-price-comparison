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


# ── Taiwan extra scrapers ────────────────────────────────────────────────────

async def _scrape_shopee_tw(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """蝦皮購物 (Shopee TW) semi-public search API."""
    url = (
        f"https://shopee.tw/api/v4/search/search_items"
        f"?by=relevancy&keyword={quote(keyword)}&limit=8&newest=0"
        f"&order=desc&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"
    )
    try:
        resp = await client.get(url, headers={
            **_HEADERS_TW,
            "Accept": "application/json",
            "Referer": f"https://shopee.tw/search?keyword={quote(keyword)}",
            "X-API-SOURCE": "pc",
            "X-Requested-With": "XMLHttpRequest",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        items = data.get("items") or data.get("data", {}).get("items", [])
        for entry in items[:8]:
            item = entry.get("item_basic") or entry
            name = (item.get("name") or "").strip()
            # Shopee prices are in "cents" (TWD * 100000)
            price_raw = item.get("price") or item.get("price_min") or 0
            price = float(price_raw) / 100000 if price_raw > 100000 else float(price_raw)
            item_id = item.get("itemid") or item.get("item_id", "")
            shop_id = item.get("shopid") or item.get("shop_id", "")
            if name and price > 1:
                results.append(PriceListing(
                    platform="蝦皮購物",
                    title=name,
                    price=price,
                    currency="TWD",
                    url=f"https://shopee.tw/product/{shop_id}/{item_id}",
                ))
        results = _filter_outliers(results)[:5]
        logger.info("Shopee TW: %d results for '%s'", len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("Shopee TW scrape failed for '%s': %s", keyword, exc)
        return []


async def _scrape_yahoo_tw(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Yahoo購物中心 (Taiwan) HTML search."""
    url = f"https://tw.buy.yahoo.com/search/product?p={quote(keyword)}&sort=pop"
    try:
        resp = await client.get(url, headers=_HEADERS_TW, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select("li.LoopGrid-item, li[class*='GridProduct']")[:8]:
            title_el = card.select_one("p.Ell, h3, [class*='title']")
            price_el = card.select_one("[class*='price'], [class*='Price']")
            link_el = card.select_one("a[href]")
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://tw.buy.yahoo.com{href}"
                results.append(PriceListing(
                    platform="Yahoo購物中心",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="TWD",
                    url=full_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:5]
        logger.info("Yahoo TW: %d results for '%s'", len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("Yahoo TW scrape failed for '%s': %s", keyword, exc)
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


async def _scrape_amazon_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Amazon Japan HTML search – uses CloudFront CDN, less aggressively blocked."""
    url = f"https://www.amazon.co.jp/s?k={quote(keyword)}&language=ja_JP"
    try:
        resp = await client.get(url, headers={
            **_HEADERS_JP,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select('div[data-component-type="s-search-result"]')[:8]:
            title_el = card.select_one("h2 span.a-text-normal, h2 span")
            price_whole = card.select_one("span.a-price-whole")
            link_el = card.select_one("h2 a.a-link-normal")
            if not (title_el and price_whole):
                continue
            try:
                price_raw = "".join(c for c in price_whole.text if c.isdigit())
                if not price_raw:
                    continue
                href = link_el.get("href", "") if link_el else ""
                full_url = f"https://www.amazon.co.jp{href}" if href.startswith("/") else href
                results.append(PriceListing(
                    platform="Amazon Japan",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="JPY",
                    url=full_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:5]
        logger.info("Amazon JP: %d results for '%s'", len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("Amazon JP scrape failed for '%s': %s", keyword, exc)
        return []


async def _scrape_kakaku_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """価格.com (Kakaku) – Japan's largest price comparison site."""
    url = f"https://kakaku.com/search_results/{quote(keyword)}/?category=&stype=0&tab=product"
    try:
        resp = await client.get(url, headers=_HEADERS_JP, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select("li.ckitanker, div.ckitanker, li[class*='Product']")[:8]:
            title_el = card.select_one("p.ckitanker_name a, .p-item_name a, h2 a, a.p-item_name")
            price_el = card.select_one("span.priceTxt, .p-item_price strong, [class*='price']")
            link_el = title_el if title_el else card.select_one("a[href]")
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://kakaku.com{href}"
                results.append(PriceListing(
                    platform="価格.com",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="JPY",
                    url=full_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:5]
        logger.info("Kakaku JP: %d results for '%s'", len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("Kakaku JP scrape failed for '%s': %s", keyword, exc)
        return []


# ── Platform search URL lookup ───────────────────────────────────────────────

_PLATFORM_SEARCH_URLS: dict[str, str] = {
    "pchome":          "https://24h.pchome.com.tw/search/?q={kw}",
    "momo":            "https://www.momoshop.com.tw/search/searchShop.jsp?keyword={kw}",
    "蝦皮":            "https://shopee.tw/search?keyword={kw}",
    "shopee":          "https://shopee.tw/search?keyword={kw}",
    "yahoo購物":       "https://tw.buy.yahoo.com/search/product?p={kw}",
    "燦坤":            "https://www.tkec.com.tw/search.aspx?q={kw}",
    "博客來":          "https://search.books.com.tw/search/query/key/{kw}",
    "楽天":            "https://search.rakuten.co.jp/search/mall/{kw}/",
    "rakuten":         "https://search.rakuten.co.jp/search/mall/{kw}/",
    "yahoo!ショッピング": "https://shopping.yahoo.co.jp/search?p={kw}",
    "yahoo!shopping":  "https://shopping.yahoo.co.jp/search?p={kw}",
    "amazon":          "https://www.amazon.co.jp/s?k={kw}",
    "価格.com":        "https://kakaku.com/search_results/{kw}/",
    "kakaku":          "https://kakaku.com/search_results/{kw}/",
    "ヨドバシ":        "https://www.yodobashi.com/?word={kw}",
    "yodobashi":       "https://www.yodobashi.com/?word={kw}",
    "ビックカメラ":    "https://www.biccamera.com/bc/s/?q={kw}",
    "biccamera":       "https://www.biccamera.com/bc/s/?q={kw}",
}


def _platform_search_url(platform: str, keyword: str) -> str:
    """Return a guaranteed-valid search URL for the given platform + keyword."""
    pl = platform.lower()
    kw = quote(keyword)
    for key, tmpl in _PLATFORM_SEARCH_URLS.items():
        if key in pl:
            return tmpl.format(kw=kw)
    # Generic Google Shopping fallback
    return f"https://www.google.com/search?q={quote(platform)}+{kw}&tbm=shop"


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
            f'Search Google Shopping and Google Search for the current retail price of '
            f'"{keyword}" in Taiwan (台灣).\n'
            f"Check these platforms: PChome 24h, momo購物網, 蝦皮購物(Shopee), "
            f"Yahoo購物中心, 燦坤, 博客來.\n\n"
            f"IMPORTANT: Only include results for the EXACT product \"{keyword}\", "
            f"not accessories or unrelated items. Prices must be in TWD and realistic.\n\n"
            f"Return ONLY a JSON array with NO url field (no markdown, no explanation):\n"
            f'[{{"platform":"PChome 24h","title":"exact full product name","price":9490,'
            f'"currency":"TWD"}}]\n\n'
            f"Include 4-6 results from different stores."
        )
        currency = "TWD"
    else:
        prompt = (
            f'Search Google Shopping and Google Search for the current retail price of '
            f'"{keyword}" in Japan (日本).\n'
            f"Check these platforms: 楽天市場, Yahoo!ショッピング, Amazon.co.jp, "
            f"ヨドバシカメラ, ビックカメラ, 価格.com.\n\n"
            f"IMPORTANT: Only include results for the EXACT product \"{keyword}\", "
            f"not accessories. Prices must be in JPY and realistic.\n\n"
            f"Return ONLY a JSON array with NO url field (no markdown, no explanation):\n"
            f'[{{"platform":"楽天市場","title":"exact full product name","price":37980,'
            f'"currency":"JPY"}}]\n\n'
            f"Include 4-6 results from different stores."
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
            platform = str(item.get("platform", "電商平台"))
            if price > 0 and title:
                results.append(PriceListing(
                    platform=platform,
                    title=title,
                    price=price,
                    currency=str(item.get("currency", currency)),
                    # Always use a guaranteed-valid search URL, never Gemini's hallucinated product URL
                    url=_platform_search_url(platform, keyword),
                ))
        logger.info("Gemini fallback (%s): %d results for '%s'", market, len(results), keyword)
        return results
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse Gemini price response for '%s': %s | text: %.200s", keyword, exc, text)
        return []


# ── Public API ───────────────────────────────────────────────────────────────

async def fetch_tw_prices(keyword: str) -> list[PriceListing]:
    """Return Taiwan listings – PChome + momo + Shopee + Yahoo TW, with Gemini fallback."""
    settings = get_settings()
    if settings.app_env != "production":
        logger.debug("DEV mock TW prices for '%s'", keyword)
        await asyncio.sleep(0.05)
        return _mock_tw_prices(keyword)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        results_per_source = await asyncio.gather(
            _scrape_pchome(client, keyword),
            _scrape_momo(client, keyword),
            _scrape_shopee_tw(client, keyword),
            _scrape_yahoo_tw(client, keyword),
        )
    combined = [r for src in results_per_source for r in src]
    await asyncio.sleep(settings.scraper_request_delay)

    if not combined:
        logger.warning("All TW scrapers failed for '%s', falling back to Gemini Search", keyword)
        combined = await _fallback_prices_via_gemini(keyword, "TW")

    logger.info("TW total: %d listings for '%s'", len(combined), keyword)
    return combined


async def fetch_jp_prices(keyword: str) -> list[PriceListing]:
    """Return Japan listings – Rakuten + Yahoo + Amazon + Kakaku, with Gemini fallback."""
    settings = get_settings()
    if settings.app_env != "production":
        logger.debug("DEV mock JP prices for '%s'", keyword)
        await asyncio.sleep(0.05)
        return _mock_jp_prices(keyword)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        results_per_source = await asyncio.gather(
            _scrape_rakuten_jp(client, keyword),
            _scrape_yahoo_shopping_jp(client, keyword),
            _scrape_amazon_jp(client, keyword),
            _scrape_kakaku_jp(client, keyword),
        )
    combined = [r for src in results_per_source for r in src]
    await asyncio.sleep(settings.scraper_request_delay)

    if not combined:
        logger.warning("All JP scrapers failed for '%s', falling back to Gemini Search", keyword)
        combined = await _fallback_prices_via_gemini(keyword, "JP")

    logger.info("JP total: %d listings for '%s'", len(combined), keyword)
    return combined
