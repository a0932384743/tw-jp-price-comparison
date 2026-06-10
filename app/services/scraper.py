"""
Price Scraper – Taiwan & Japan e-commerce platforms.

Production runs concurrent real HTTP scrapers:
  Taiwan:  PChome 24h (JSON API) + momo購物網 (HTML) + 蝦皮購物 (API)
           + Yahoo TW (HTML) + 露天拍賣 (API)
           + brand stores (UNIQLO TW / GU TW / Nike TW / Adidas TW) when AI selects them
  Japan:   楽天市場 (HTML/API) + Yahoo!ショッピング (HTML/API)
           + Amazon Japan (HTML) + 価格.com (HTML)
           + brand stores (UNIQLO JP / GU JP / Nike JP / Adidas JP) when AI selects them

Development uses deterministic mock data so the pipeline works
without hitting live sites (toggle via APP_ENV).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import time
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

def _filter_outliers(listings: list[PriceListing], min_ratio: float = 0.40) -> list[PriceListing]:
    """Remove listings whose price is far below the group median (likely accessories/unrelated).

    Uses min_ratio=0.40: keeps items priced at ≥40% of median, so accessories
    costing a fraction of the main product are excluded while genuine bargains remain.
    Results are returned sorted by price ascending so the cheapest appears first.
    """
    if len(listings) <= 1:
        return sorted(listings, key=lambda l: l.price)
    prices = sorted(l.price for l in listings)
    median = prices[len(prices) // 2]
    filtered = [l for l in listings if l.price >= median * min_ratio]
    return sorted(filtered, key=lambda l: l.price)


def _dedup_cheapest_per_platform(listings: list[PriceListing]) -> list[PriceListing]:
    """Keep only the single cheapest listing per platform.

    Eliminates duplicate cards from the same store, ensuring each e-commerce
    platform appears at most once with its best available price.
    """
    seen: dict[str, PriceListing] = {}
    for l in sorted(listings, key=lambda x: x.price):
        if l.platform not in seen:
            seen[l.platform] = l
    return sorted(seen.values(), key=lambda x: x.price)


def _filter_relevant(listings: list[PriceListing], keyword: str) -> list[PriceListing]:
    """Drop listings whose title shares no token with the search keyword.

    Uses a lenient rule: only filters a listing when NONE of the keyword tokens
    (length ≥ 2) appear in the title. Falls back to the full list if all are
    filtered to avoid returning nothing on CJK / cross-language mismatches.
    """
    tokens = [t.lower() for t in re.split(r'[\s\-_/()\[\]·・]+', keyword) if len(t) >= 2]
    if not tokens:
        return listings

    def _matches(title: str) -> bool:
        tl = title.lower()
        return any(tok in tl for tok in tokens)

    relevant = [l for l in listings if _matches(l.title)]
    return relevant if relevant else listings  # never return empty


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
                     url=f"https://www.momoshop.com.tw/search/searchShop.jsp?keyword={kw}",
                     data_source="scraped"),
        PriceListing(platform="蝦皮購物 (Shopee TW)", title=f"{keyword} 台灣賣家 快速出貨",
                     price=float(rng.randint(int(base * 0.85), int(base * 0.95))), currency="TWD",
                     url=f"https://shopee.tw/search?keyword={kw}",
                     data_source="scraped"),
        PriceListing(platform="PChome 24h", title=f"{keyword} PChome獨家優惠",
                     price=float(rng.randint(int(base * 0.90), int(base * 1.05))), currency="TWD",
                     url=f"https://24h.pchome.com.tw/search/?q={kw}",
                     data_source="scraped"),
    ]


def _mock_jp_prices(keyword: str) -> list[PriceListing]:
    rng = random.Random(_seed_from(keyword) ^ 0xDEADBEEF)
    base = rng.randint(4000, 35000)
    kw = quote(keyword)
    return [
        PriceListing(platform="楽天市場", title=f"{keyword} 楽天最安値 送料無料",
                     price=float(base), currency="JPY",
                     url=f"https://search.rakuten.co.jp/search/mall/{kw}/",
                     data_source="scraped"),
        PriceListing(platform="Yahoo!ショッピング", title=f"{keyword} Yahoo限定セール",
                     price=float(rng.randint(int(base * 0.90), int(base * 1.02))), currency="JPY",
                     url=f"https://shopping.yahoo.co.jp/search?p={kw}",
                     data_source="scraped"),
        PriceListing(platform="Amazon Japan", title=f"{keyword} Amazon正規品",
                     price=float(rng.randint(int(base * 0.88), int(base * 0.98))), currency="JPY",
                     url=f"https://www.amazon.co.jp/s?k={kw}",
                     data_source="scraped"),
    ]


# ── Taiwan live scrapers ─────────────────────────────────────────────────────

async def _scrape_pchome(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """PChome 24h JSON search API – sorted by price ascending to get cheapest first."""
    url = (
        f"https://ecshweb.pchome.com.tw/search/v3.3/all/results"
        f"?q={quote(keyword)}&page=1&sort=price/ac"
    )
    try:
        t0 = time.perf_counter()
        logger.info("→ [PChome] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_TW, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for prod in data.get("Prods", [])[:8]:
            name = prod.get("Name", "").strip()
            price = prod.get("Price", {}).get("P") or prod.get("Price", {}).get("M")
            prod_id = prod.get("Id", "")
            pic = prod.get("Pic", "").lstrip("/")
            # PChome Pic field may already include "items/" prefix
            if pic:
                base = pic if pic.startswith("items/") else f"items/{pic}"
                image_url = f"https://a.ecimg.tw/{base}"
            else:
                image_url = None
            if name and price:
                results.append(PriceListing(
                    platform="PChome 24h",
                    title=name,
                    price=float(price),
                    currency="TWD",
                    url=f"https://24h.pchome.com.tw/prod/{prod_id}",
                    image_url=image_url,
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [PChome] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [PChome] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_momo(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """momo購物網 HTML search."""
    url = (
        f"https://www.momoshop.com.tw/search/searchShop.jsp"
        f"?keyword={quote(keyword)}&searchType=1&cateLevel=0&ent=k&userIN={quote(keyword)}"
    )
    try:
        t0 = time.perf_counter()
        logger.info("→ [momo] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_TW, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select("li.goodsItem")[:8]:
            title_el = card.select_one(".prdName")
            price_el = card.select_one(".price b")
            link_el = card.select_one("a")
            img_el = card.select_one("img[src], img[data-src]")
            if not (title_el and price_el):
                continue
            try:
                price = float(price_el.text.strip().replace(",", ""))
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.momoshop.com.tw{href}"
                raw_img = img_el.get("src") or img_el.get("data-src") if img_el else None
                image_url = raw_img if raw_img and raw_img.startswith("http") else None
                results.append(PriceListing(
                    platform="momo購物網",
                    title=title_el.text.strip(),
                    price=price,
                    currency="TWD",
                    url=full_url,
                    image_url=image_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:3]
        logger.info("← [momo] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [momo] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
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
        t0 = time.perf_counter()
        logger.info("→ [蝦皮] querying '%s'", keyword)
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
            # Shopee prices are in "cents" (TWD * 100000).
            # Use price_min first – for multi-variant items this is the cheapest option.
            price_raw = item.get("price_min") or item.get("price") or 0
            price = float(price_raw) / 100000 if price_raw > 100000 else float(price_raw)
            item_id = item.get("itemid") or item.get("item_id", "")
            shop_id = item.get("shopid") or item.get("shop_id", "")
            img_hash = item.get("image") or (item.get("images") or [None])[0]
            # Use full CDN URL (no suffix = original quality); _tn is only 100×100
            image_url = f"https://cf.shopee.tw/file/{img_hash}" if img_hash else None
            if name and price > 1:
                results.append(PriceListing(
                    platform="蝦皮購物",
                    title=name,
                    price=price,
                    currency="TWD",
                    url=f"https://shopee.tw/product/{shop_id}/{item_id}",
                    image_url=image_url,
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [蝦皮] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [蝦皮] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_yahoo_tw(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Yahoo購物中心 (Taiwan) HTML search."""
    url = f"https://tw.buy.yahoo.com/search/product?p={quote(keyword)}&sort=pop"
    try:
        t0 = time.perf_counter()
        logger.info("→ [Yahoo TW] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_TW, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select("li.LoopGrid-item, li[class*='GridProduct']")[:8]:
            title_el = card.select_one("p.Ell, h3, [class*='title']")
            price_el = card.select_one("[class*='price'], [class*='Price']")
            link_el = card.select_one("a[href]")
            img_el = card.select_one("img[src], img[data-src]")
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://tw.buy.yahoo.com{href}"
                raw_img = img_el.get("src") or img_el.get("data-src") if img_el else None
                image_url = raw_img if raw_img and raw_img.startswith("http") else None
                results.append(PriceListing(
                    platform="Yahoo購物中心",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="TWD",
                    url=full_url,
                    image_url=image_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:3]
        logger.info("← [Yahoo TW] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Yahoo TW] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_ruten_tw(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """露天拍賣 – public JSON API, sorted by price ascending, no auth required."""
    t0 = time.perf_counter()
    url = (
        f"https://rtapi.ruten.com.tw/api/search/v3/index.php/core/prod"
        f"?q={quote(keyword)}&type=direct&start=0&limit=10&sort=prc_asc"
    )
    try:
        logger.info("→ [露天拍賣] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_TW, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for row in data.get("Rows", [])[:8]:
            name = (row.get("Name") or "").strip()
            price_range = row.get("PriceRange") or {}
            price = price_range.get("Lowest") or price_range.get("Highest") or 0
            prod_id = row.get("Id", "")
            images = row.get("Image") or {}
            img = images.get("Url") or ""
            image_url = img if img.startswith("https://") else None
            if name and price:
                results.append(PriceListing(
                    platform="露天拍賣",
                    title=name,
                    price=float(price),
                    currency="TWD",
                    url=f"https://goods.ruten.com.tw/item/show?{prod_id}" if prod_id else "https://www.ruten.com.tw",
                    image_url=image_url,
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [露天拍賣] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [露天拍賣] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


# ── Brand official APIs (Taiwan) ────────────────────────────────────────────

async def _scrape_uniqlo_tw(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """UNIQLO Taiwan official search API – no auth required."""
    t0 = time.perf_counter()
    url = (
        f"https://www.uniqlo.com/tw/api/commerce/v5/zh_TW/search"
        f"?q={quote(keyword)}&offset=0&limit=8&httpFailure=true"
    )
    try:
        logger.info("→ [UNIQLO TW] querying '%s'", keyword)
        resp = await client.get(url, headers={
            **_HEADERS_TW,
            "Origin": "https://www.uniqlo.com",
            "Referer": f"https://www.uniqlo.com/tw/search?q={quote(keyword)}",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for item in (data.get("result") or {}).get("items", [])[:8]:
            name = (item.get("name") or "").strip()
            prices = item.get("prices") or {}
            promo = prices.get("promo") or {}
            base = prices.get("base") or {}
            price = promo.get("value") or base.get("value") or 0
            product_id = item.get("productId", "")
            main_pic = item.get("mainPic") or ""
            if main_pic.startswith("/"):
                image_url: str | None = f"https://image.uniqlo.com{main_pic}"
            elif main_pic.startswith("https://"):
                image_url = main_pic
            else:
                image_url = None
            if name and price:
                results.append(PriceListing(
                    platform="UNIQLO 台灣",
                    title=name,
                    price=float(price),
                    currency="TWD",
                    url=f"https://www.uniqlo.com/tw/products/{product_id}/00" if product_id else "https://www.uniqlo.com/tw",
                    image_url=image_url,
                    data_source="scraped",
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [UNIQLO TW] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [UNIQLO TW] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_gu_tw(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """GU Taiwan official search API – no auth required."""
    t0 = time.perf_counter()
    url = (
        f"https://www.gu-global.com/tw/api/commerce/v5/zh_TW/search"
        f"?q={quote(keyword)}&offset=0&limit=8&httpFailure=true"
    )
    try:
        logger.info("→ [GU TW] querying '%s'", keyword)
        resp = await client.get(url, headers={
            **_HEADERS_TW,
            "Origin": "https://www.gu-global.com",
            "Referer": f"https://www.gu-global.com/tw/search?q={quote(keyword)}",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for item in (data.get("result") or {}).get("items", [])[:8]:
            name = (item.get("name") or "").strip()
            prices = item.get("prices") or {}
            promo = prices.get("promo") or {}
            base = prices.get("base") or {}
            price = promo.get("value") or base.get("value") or 0
            product_id = item.get("productId", "")
            main_pic = item.get("mainPic") or ""
            if main_pic.startswith("/"):
                image_url: str | None = f"https://image.gu-global.com{main_pic}"
            elif main_pic.startswith("https://"):
                image_url = main_pic
            else:
                image_url = None
            if name and price:
                results.append(PriceListing(
                    platform="GU 台灣",
                    title=name,
                    price=float(price),
                    currency="TWD",
                    url=f"https://www.gu-global.com/tw/products/{product_id}/00" if product_id else "https://www.gu-global.com/tw",
                    image_url=image_url,
                    data_source="scraped",
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [GU TW] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [GU TW] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


# ── Japan live scrapers ──────────────────────────────────────────────────────

async def _scrape_rakuten_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """楽天市場 HTML search."""
    url = f"https://search.rakuten.co.jp/search/mall/{quote(keyword)}/"
    try:
        t0 = time.perf_counter()
        logger.info("→ [楽天HTML] querying '%s'", keyword)
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
            img_el = card.select_one("img[src]")
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                raw_img = img_el.get("src") if img_el else None
                image_url = raw_img if raw_img and raw_img.startswith("http") else None
                results.append(PriceListing(
                    platform="楽天市場",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="JPY",
                    url=title_el.get("href", ""),
                    image_url=image_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:3]
        logger.info("← [楽天HTML] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [楽天HTML] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_yahoo_shopping_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Yahoo!ショッピング – try __NEXT_DATA__ JSON first, then HTML fallback."""
    url = f"https://shopping.yahoo.co.jp/search?p={quote(keyword)}&sort=-score"
    try:
        t0 = time.perf_counter()
        logger.info("→ [Yahoo JP HTML] querying '%s'", keyword)
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
                    raw_img = item.get("image") or item.get("imageUrl") or ""
                    image_url = str(raw_img) if raw_img and str(raw_img).startswith("http") else None
                    if name and price:
                        results.append(PriceListing(
                            platform="Yahoo!ショッピング",
                            title=str(name).strip(),
                            price=float(price),
                            currency="JPY",
                            url=str(item_url),
                            image_url=image_url,
                        ))
                if results:
                    logger.info("← [Yahoo JP HTML] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
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
            img_el = card.select_one("img[src]")
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                href = title_el.get("href", "")
                raw_img = img_el.get("src") if img_el else None
                image_url = raw_img if raw_img and raw_img.startswith("http") else None
                results.append(PriceListing(
                    platform="Yahoo!ショッピング",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="JPY",
                    url=href if href.startswith("http") else f"https://shopping.yahoo.co.jp{href}",
                    image_url=image_url,
                ))
            except (ValueError, AttributeError):
                continue

        logger.info("← [Yahoo JP HTML] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Yahoo JP HTML] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_amazon_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Amazon Japan HTML search – uses CloudFront CDN, less aggressively blocked."""
    url = f"https://www.amazon.co.jp/s?k={quote(keyword)}&language=ja_JP"
    try:
        t0 = time.perf_counter()
        logger.info("→ [Amazon JP] querying '%s'", keyword)
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
            img_el = card.select_one("img.s-image")
            if not (title_el and price_whole):
                continue
            try:
                price_raw = "".join(c for c in price_whole.text if c.isdigit())
                if not price_raw:
                    continue
                href = link_el.get("href", "") if link_el else ""
                full_url = f"https://www.amazon.co.jp{href}" if href.startswith("/") else href
                raw_img = img_el.get("src") if img_el else None
                image_url = raw_img if raw_img and raw_img.startswith("http") else None
                results.append(PriceListing(
                    platform="Amazon Japan",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="JPY",
                    url=full_url,
                    image_url=image_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:3]
        logger.info("← [Amazon JP] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Amazon JP] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_kakaku_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """価格.com (Kakaku) – Japan's largest price comparison site."""
    url = f"https://kakaku.com/search_results/{quote(keyword)}/?category=&stype=0&tab=product"
    try:
        t0 = time.perf_counter()
        logger.info("→ [Kakaku] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_JP, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []
        for card in soup.select("li.ckitanker, div.ckitanker, li[class*='Product']")[:8]:
            title_el = card.select_one("p.ckitanker_name a, .p-item_name a, h2 a, a.p-item_name")
            price_el = card.select_one("span.priceTxt, .p-item_price strong, [class*='price']")
            link_el = title_el if title_el else card.select_one("a[href]")
            img_el = card.select_one("img[src]")
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://kakaku.com{href}"
                raw_img = img_el.get("src") if img_el else None
                image_url = raw_img if raw_img and raw_img.startswith("http") else None
                results.append(PriceListing(
                    platform="価格.com",
                    title=title_el.text.strip(),
                    price=float(price_raw),
                    currency="JPY",
                    url=full_url,
                    image_url=image_url,
                ))
            except (ValueError, AttributeError):
                continue
        results = _filter_outliers(results)[:3]
        logger.info("← [Kakaku] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Kakaku] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


# ── Brand official APIs (Japan) ─────────────────────────────────────────────

async def _scrape_uniqlo_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """UNIQLO Japan official search API – no auth required."""
    t0 = time.perf_counter()
    url = (
        f"https://www.uniqlo.com/jp/api/commerce/v5/ja_JP/search"
        f"?q={quote(keyword)}&offset=0&limit=8&httpFailure=true"
    )
    try:
        logger.info("→ [UNIQLO JP] querying '%s'", keyword)
        resp = await client.get(url, headers={
            **_HEADERS_JP,
            "Origin": "https://www.uniqlo.com",
            "Referer": f"https://www.uniqlo.com/jp/search?q={quote(keyword)}",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for item in (data.get("result") or {}).get("items", [])[:8]:
            name = (item.get("name") or "").strip()
            prices = item.get("prices") or {}
            promo = prices.get("promo") or {}
            base = prices.get("base") or {}
            price = promo.get("value") or base.get("value") or 0
            product_id = item.get("productId", "")
            main_pic = item.get("mainPic") or ""
            if main_pic.startswith("/"):
                image_url: str | None = f"https://image.uniqlo.com{main_pic}"
            elif main_pic.startswith("https://"):
                image_url = main_pic
            else:
                image_url = None
            if name and price:
                results.append(PriceListing(
                    platform="UNIQLO 日本",
                    title=name,
                    price=float(price),
                    currency="JPY",
                    url=f"https://www.uniqlo.com/jp/products/{product_id}/00" if product_id else "https://www.uniqlo.com/jp",
                    image_url=image_url,
                    data_source="scraped",
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [UNIQLO JP] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [UNIQLO JP] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_gu_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """GU Japan official search API – no auth required."""
    t0 = time.perf_counter()
    url = (
        f"https://www.gu-global.com/jp/api/commerce/v5/ja_JP/search"
        f"?q={quote(keyword)}&offset=0&limit=8&httpFailure=true"
    )
    try:
        logger.info("→ [GU JP] querying '%s'", keyword)
        resp = await client.get(url, headers={
            **_HEADERS_JP,
            "Origin": "https://www.gu-global.com",
            "Referer": f"https://www.gu-global.com/jp/search?q={quote(keyword)}",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for item in (data.get("result") or {}).get("items", [])[:8]:
            name = (item.get("name") or "").strip()
            prices = item.get("prices") or {}
            promo = prices.get("promo") or {}
            base = prices.get("base") or {}
            price = promo.get("value") or base.get("value") or 0
            product_id = item.get("productId", "")
            main_pic = item.get("mainPic") or ""
            if main_pic.startswith("/"):
                image_url: str | None = f"https://image.gu-global.com{main_pic}"
            elif main_pic.startswith("https://"):
                image_url = main_pic
            else:
                image_url = None
            if name and price:
                results.append(PriceListing(
                    platform="GU 日本",
                    title=name,
                    price=float(price),
                    currency="JPY",
                    url=f"https://www.gu-global.com/jp/products/{product_id}/00" if product_id else "https://www.gu-global.com/jp",
                    image_url=image_url,
                    data_source="scraped",
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [GU JP] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [GU JP] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


# ── Brand official websites (Nike & Adidas) ──────────────────────────────────

async def _scrape_nike_tw(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Nike Taiwan official website – __NEXT_DATA__ JSON then HTML fallback."""
    t0 = time.perf_counter()
    url = f"https://www.nike.com/tw/w?q={quote(keyword)}&vst={quote(keyword)}"
    try:
        logger.info("→ [Nike TW] querying '%s'", keyword)
        resp = await client.get(url, headers={**_HEADERS_TW, "Accept": "text/html,application/xhtml+xml"}, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []

        next_script = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_script and next_script.string:
            try:
                next_data = json.loads(next_script.string)
                products = (
                    next_data.get("props", {}).get("pageProps", {})
                    .get("initialState", {}).get("Wall", {}).get("products", [])
                )
                for prod in products[:8]:
                    name = prod.get("title", "").strip()
                    subtitle = prod.get("subtitle", "")
                    full_name = f"{name} {subtitle}".strip() if subtitle else name
                    price_data = prod.get("price", {})
                    price = price_data.get("currentPrice") or price_data.get("fullPrice") or 0
                    pid = prod.get("cloudProductId") or prod.get("pid") or ""
                    imgs = prod.get("images") or [{}]
                    img_url = imgs[0].get("src") if imgs else None
                    prod_url = f"https://www.nike.com/tw/t/{pid}" if pid else "https://www.nike.com/tw"
                    if full_name and price:
                        results.append(PriceListing(
                            platform="Nike 台灣", title=full_name, price=float(price),
                            currency="TWD", url=prod_url, image_url=img_url, data_source="scraped",
                        ))
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass

        if not results:
            for card in soup.select("div.product-card, article.product-card")[:8]:
                title_el = card.select_one(".product-card__title, [class*='title']")
                price_el = card.select_one(".product-price, [class*='price']")
                link_el  = card.select_one("a[href]")
                img_el   = card.select_one("img[src]")
                if not (title_el and price_el):
                    continue
                try:
                    price_raw = "".join(c for c in price_el.text if c.isdigit())
                    if not price_raw:
                        continue
                    href = link_el.get("href", "") if link_el else ""
                    full_url = href if href.startswith("http") else f"https://www.nike.com{href}"
                    raw_img = img_el.get("src") if img_el else None
                    results.append(PriceListing(
                        platform="Nike 台灣", title=title_el.text.strip(), price=float(price_raw),
                        currency="TWD", url=full_url,
                        image_url=raw_img if raw_img and raw_img.startswith("http") else None,
                        data_source="scraped",
                    ))
                except (ValueError, AttributeError):
                    continue

        results = _filter_outliers(results)[:3]
        logger.info("← [Nike TW] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Nike TW] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_nike_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Nike Japan official website – __NEXT_DATA__ JSON then HTML fallback."""
    t0 = time.perf_counter()
    url = f"https://www.nike.com/jp/w?q={quote(keyword)}&vst={quote(keyword)}"
    try:
        logger.info("→ [Nike JP] querying '%s'", keyword)
        resp = await client.get(url, headers={**_HEADERS_JP, "Accept": "text/html,application/xhtml+xml"}, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []

        next_script = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_script and next_script.string:
            try:
                next_data = json.loads(next_script.string)
                products = (
                    next_data.get("props", {}).get("pageProps", {})
                    .get("initialState", {}).get("Wall", {}).get("products", [])
                )
                for prod in products[:8]:
                    name = prod.get("title", "").strip()
                    subtitle = prod.get("subtitle", "")
                    full_name = f"{name} {subtitle}".strip() if subtitle else name
                    price_data = prod.get("price", {})
                    price = price_data.get("currentPrice") or price_data.get("fullPrice") or 0
                    pid = prod.get("cloudProductId") or prod.get("pid") or ""
                    imgs = prod.get("images") or [{}]
                    img_url = imgs[0].get("src") if imgs else None
                    prod_url = f"https://www.nike.com/jp/t/{pid}" if pid else "https://www.nike.com/jp"
                    if full_name and price:
                        results.append(PriceListing(
                            platform="Nike 日本", title=full_name, price=float(price),
                            currency="JPY", url=prod_url, image_url=img_url, data_source="scraped",
                        ))
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass

        if not results:
            for card in soup.select("div.product-card, article.product-card")[:8]:
                title_el = card.select_one(".product-card__title, [class*='title']")
                price_el = card.select_one(".product-price, [class*='price']")
                link_el  = card.select_one("a[href]")
                img_el   = card.select_one("img[src]")
                if not (title_el and price_el):
                    continue
                try:
                    price_raw = "".join(c for c in price_el.text if c.isdigit())
                    if not price_raw:
                        continue
                    href = link_el.get("href", "") if link_el else ""
                    full_url = href if href.startswith("http") else f"https://www.nike.com{href}"
                    raw_img = img_el.get("src") if img_el else None
                    results.append(PriceListing(
                        platform="Nike 日本", title=title_el.text.strip(), price=float(price_raw),
                        currency="JPY", url=full_url,
                        image_url=raw_img if raw_img and raw_img.startswith("http") else None,
                        data_source="scraped",
                    ))
                except (ValueError, AttributeError):
                    continue

        results = _filter_outliers(results)[:3]
        logger.info("← [Nike JP] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Nike JP] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_adidas_tw(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Adidas Taiwan official website – HTML parsing."""
    t0 = time.perf_counter()
    url = f"https://shop.adidas.com.tw/search?q={quote(keyword)}"
    try:
        logger.info("→ [Adidas TW] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_TW, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []

        for card in soup.select("li.ProductCard, article[class*='ProductCard'], div[class*='ProductCard']")[:8]:
            title_el = card.select_one("p[class*='title'], h2, h3, .gl-product-card__name")
            price_el = card.select_one(".gl-price-item--sale, .gl-price-item, [class*='price']")
            link_el  = card.select_one("a[href]")
            img_el   = card.select_one("img[src], img[data-src]")
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://shop.adidas.com.tw{href}"
                raw_img = img_el.get("src") or img_el.get("data-src") if img_el else None
                results.append(PriceListing(
                    platform="Adidas 台灣", title=title_el.text.strip(), price=float(price_raw),
                    currency="TWD", url=full_url,
                    image_url=raw_img if raw_img and raw_img.startswith("http") else None,
                    data_source="scraped",
                ))
            except (ValueError, AttributeError):
                continue

        results = _filter_outliers(results)[:3]
        logger.info("← [Adidas TW] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Adidas TW] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_adidas_jp(client: httpx.AsyncClient, keyword: str) -> list[PriceListing]:
    """Adidas Japan official website – HTML parsing."""
    t0 = time.perf_counter()
    url = f"https://shop.adidas.jp/search/?query={quote(keyword)}"
    try:
        logger.info("→ [Adidas JP] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_JP, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[PriceListing] = []

        for card in soup.select("li.ProductCard, article[class*='ProductCard'], div[class*='ProductCard']")[:8]:
            title_el = card.select_one("p[class*='title'], h2, h3, .gl-product-card__name")
            price_el = card.select_one(".gl-price-item--sale, .gl-price-item, [class*='price']")
            link_el  = card.select_one("a[href]")
            img_el   = card.select_one("img[src], img[data-src]")
            if not (title_el and price_el):
                continue
            try:
                price_raw = "".join(c for c in price_el.text if c.isdigit())
                if not price_raw:
                    continue
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://shop.adidas.jp{href}"
                raw_img = img_el.get("src") or img_el.get("data-src") if img_el else None
                results.append(PriceListing(
                    platform="Adidas 日本", title=title_el.text.strip(), price=float(price_raw),
                    currency="JPY", url=full_url,
                    image_url=raw_img if raw_img and raw_img.startswith("http") else None,
                    data_source="scraped",
                ))
            except (ValueError, AttributeError):
                continue

        results = _filter_outliers(results)[:3]
        logger.info("← [Adidas JP] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Adidas JP] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


# ── Platform search URL lookup ───────────────────────────────────────────────

_PLATFORM_SEARCH_URLS: dict[str, str] = {
    "pchome":          "https://24h.pchome.com.tw/search/?q={kw}",
    "momo":            "https://www.momoshop.com.tw/search/searchShop.jsp?keyword={kw}",
    "蝦皮":            "https://shopee.tw/search?keyword={kw}",
    "shopee":          "https://shopee.tw/search?keyword={kw}",
    "yahoo購物":       "https://tw.buy.yahoo.com/search/product?p={kw}",
    "露天":            "https://www.ruten.com.tw/find/?q={kw}",
    "博客來":          "https://search.books.com.tw/search/query/key/{kw}",
    "uniqlo 台灣":     "https://www.uniqlo.com/tw/search?q={kw}",
    "uniqlo 日本":     "https://www.uniqlo.com/jp/search?q={kw}",
    "gu 台灣":         "https://www.gu-global.com/tw/search?q={kw}",
    "gu 日本":         "https://www.gu-global.com/jp/search?q={kw}",
    "楽天":            "https://search.rakuten.co.jp/search/mall/{kw}/",
    "rakuten":         "https://search.rakuten.co.jp/search/mall/{kw}/",
    "yahoo!ショッピング": "https://shopping.yahoo.co.jp/search?p={kw}",
    "yahoo!shopping":  "https://shopping.yahoo.co.jp/search?p={kw}",
    "amazon":          "https://www.amazon.co.jp/s?k={kw}",
    "価格.com":        "https://kakaku.com/search_results/{kw}/",
    "kakaku":          "https://kakaku.com/search_results/{kw}/",
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


# ── SerpAPI Google Shopping (works from any cloud IP) ───────────────────────

async def _scrape_serpapi_tw(client: httpx.AsyncClient, keyword: str, api_key: str) -> list[PriceListing]:
    """Google Shopping Taiwan via SerpApi – bypasses IP blocks, free tier = 100/month.

    Returns real storefront prices aggregated by Google Shopping (gl=tw, currency=TWD).
    """
    t0 = time.perf_counter()
    logger.info("→ [SerpAPI TW] querying '%s'", keyword)
    try:
        resp = await client.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_shopping", "q": keyword,
                    "gl": "tw", "hl": "zh-tw", "api_key": api_key, "num": 10},
            timeout=20,
        )
        if resp.status_code == 429:
            logger.warning("SerpApi monthly quota reached (TW shopping)")
            return []
        resp.raise_for_status()
        results: list[PriceListing] = []
        for item in resp.json().get("shopping_results", [])[:10]:
            title = (item.get("title") or "").strip()
            price_str = item.get("price") or ""
            price_digits = re.sub(r"[^\d]", "", price_str)
            if not title or not price_digits:
                continue
            price = float(price_digits)
            if price < 10:
                continue
            source = item.get("source") or "Google Shopping"
            link = (item.get("link") or item.get("product_link")
                    or f"https://www.google.com/search?q={quote(keyword)}&tbm=shop")
            thumb = item.get("thumbnail") or None
            results.append(PriceListing(
                platform=source,
                title=title,
                price=price,
                currency="TWD",
                url=link,
                image_url=thumb if thumb and str(thumb).startswith("https://") else None,
                data_source="scraped",
            ))
        results = _filter_outliers(results)[:5]
        logger.info("← [SerpAPI TW] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [SerpAPI TW] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_serpapi_jp(client: httpx.AsyncClient, keyword: str, api_key: str) -> list[PriceListing]:
    """Google Shopping Japan via SerpApi – bypasses IP blocks, free tier = 100/month.

    Returns real storefront prices aggregated by Google Shopping (gl=jp, currency=JPY).
    """
    t0 = time.perf_counter()
    logger.info("→ [SerpAPI JP] querying '%s'", keyword)
    try:
        resp = await client.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_shopping", "q": keyword,
                    "gl": "jp", "hl": "ja", "api_key": api_key, "num": 10},
            timeout=20,
        )
        if resp.status_code == 429:
            logger.warning("SerpApi monthly quota reached (JP shopping)")
            return []
        resp.raise_for_status()
        results: list[PriceListing] = []
        for item in resp.json().get("shopping_results", [])[:10]:
            title = (item.get("title") or "").strip()
            price_str = item.get("price") or ""
            price_digits = re.sub(r"[^\d]", "", price_str)
            if not title or not price_digits:
                continue
            price = float(price_digits)
            if price < 10:
                continue
            source = item.get("source") or "Google Shopping JP"
            link = (item.get("link") or item.get("product_link")
                    or f"https://www.google.co.jp/search?q={quote(keyword)}&tbm=shop")
            thumb = item.get("thumbnail") or None
            results.append(PriceListing(
                platform=source,
                title=title,
                price=price,
                currency="JPY",
                url=link,
                image_url=thumb if thumb and str(thumb).startswith("https://") else None,
                data_source="scraped",
            ))
        results = _filter_outliers(results)[:5]
        logger.info("← [SerpAPI JP] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [SerpAPI JP] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


# ── Japan official APIs (free, require registration) ────────────────────────

async def _scrape_rakuten_api(client: httpx.AsyncClient, keyword: str, app_id: str, affiliate_id: str = "") -> list[PriceListing]:
    """楽天市場 Ichiba Item Search API v2017 – returns reliable product images.

    Free API: register at https://webservice.rakuten.co.jp/ → set RAKUTEN_APP_ID.
    Set RAKUTEN_AFFILIATE_ID to append affiliate tracking to product URLs.
    Returns mediumImageUrls (128×128 Rakuten CDN) for each item.
    """
    params = (
        f"?applicationId={app_id}&keyword={quote(keyword)}&hits=8"
        f"&sort=%2BitemPrice&format=json&availability=1"
    )
    if affiliate_id:
        params += f"&affiliateId={affiliate_id}"
    url = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706" + params
    try:
        t0 = time.perf_counter()
        logger.info("→ [Rakuten API] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_JP, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for wrap in data.get("Items", [])[:8]:
            item = wrap.get("Item", wrap)
            name = item.get("itemName", "").strip()
            price = item.get("itemPrice", 0)
            # affiliateUrl is the tracked link when affiliateId is passed
            item_url = item.get("affiliateUrl") or item.get("itemUrl", "")

            # mediumImageUrls is list[{"imageUrl": "..."}]; smallImageUrls same shape
            image_url: str | None = None
            for key in ("mediumImageUrls", "smallImageUrls"):
                imgs = item.get(key) or []
                if imgs:
                    first = imgs[0]
                    src = first.get("imageUrl") if isinstance(first, dict) else str(first)
                    if src and src.startswith("https://"):
                        image_url = src
                        break

            if name and price:
                results.append(PriceListing(
                    platform="楽天市場",
                    title=name,
                    price=float(price),
                    currency="JPY",
                    url=item_url,
                    image_url=image_url,
                    data_source="scraped",
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [Rakuten API] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Rakuten API] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


async def _scrape_yahoo_shopping_jp_api(client: httpx.AsyncClient, keyword: str, app_id: str) -> list[PriceListing]:
    """Yahoo!ショッピング Shopping Web Service V3 API – returns CDN product images.

    Free API: register at https://developer.yahoo.co.jp/ → set YAHOO_JP_APP_ID.
    Returns image.medium (Yahoo CDN) for each item.
    """
    url = (
        "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
        f"?appid={app_id}&query={quote(keyword)}&results=8&sort=%2Bprice"
    )
    try:
        t0 = time.perf_counter()
        logger.info("→ [Yahoo JP API] querying '%s'", keyword)
        resp = await client.get(url, headers=_HEADERS_JP, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results: list[PriceListing] = []
        for hit in data.get("hits", [])[:8]:
            name = (hit.get("name") or "").strip()
            price = hit.get("price", 0)
            item_url = hit.get("url") or hit.get("externalUrl", "")

            img_obj = hit.get("image") or {}
            image_url: str | None = None
            if isinstance(img_obj, dict):
                src = img_obj.get("medium") or img_obj.get("small") or ""
                if src.startswith("https://"):
                    image_url = src

            if name and price:
                results.append(PriceListing(
                    platform="Yahoo!ショッピング",
                    title=name,
                    price=float(price),
                    currency="JPY",
                    url=item_url,
                    image_url=image_url,
                    data_source="scraped",
                ))
        results = _filter_outliers(results)[:3]
        logger.info("← [Yahoo JP API] %.2fs → %d results for '%s'", time.perf_counter() - t0, len(results), keyword)
        return results
    except Exception as exc:
        logger.warning("← [Yahoo JP API] %.2fs → failed for '%s': %s", time.perf_counter() - t0, keyword, exc)
        return []


# ── Public API ───────────────────────────────────────────────────────────────

async def fetch_tw_prices(keyword: str, brand_platforms: list[str] | None = None) -> list[PriceListing]:
    """Return Taiwan listings from real e-commerce platforms only (no AI estimation).

    brand_platforms controls which brand-official stores to include:
    'uniqlo', 'gu', 'nike', 'adidas'. Pass [] or None to skip all brand stores.
    """
    brand_platforms = brand_platforms or []
    settings = get_settings()
    if settings.app_env != "production":
        logger.debug("DEV mock TW prices for '%s'", keyword)
        await asyncio.sleep(0.05)
        return _mock_tw_prices(keyword)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        scraper_labels: list[str] = []
        tasks = []
        # SerpAPI Google Shopping works from any cloud IP — use as primary when key is set
        if settings.serpapi_key:
            scraper_labels.append("Google Shopping TW")
            tasks.append(_scrape_serpapi_tw(client, keyword, settings.serpapi_key))
        # HTML/JSON scrapers as supplement (may 403 on cloud IPs but kept for coverage)
        scraper_labels += ["PChome", "momo", "蝦皮", "Yahoo TW", "露天拍賣"]
        tasks += [
            _scrape_pchome(client, keyword),
            _scrape_momo(client, keyword),
            _scrape_shopee_tw(client, keyword),
            _scrape_yahoo_tw(client, keyword),
            _scrape_ruten_tw(client, keyword),
        ]
        if "uniqlo" in brand_platforms:
            scraper_labels.append("UNIQLO TW"); tasks.append(_scrape_uniqlo_tw(client, keyword))
        if "gu" in brand_platforms:
            scraper_labels.append("GU TW"); tasks.append(_scrape_gu_tw(client, keyword))
        if "nike" in brand_platforms:
            scraper_labels.append("Nike TW"); tasks.append(_scrape_nike_tw(client, keyword))
        if "adidas" in brand_platforms:
            scraper_labels.append("Adidas TW"); tasks.append(_scrape_adidas_tw(client, keyword))
        logger.info("→→ TW scrapers (%d): %s", len(tasks), scraper_labels)
        t_all = time.perf_counter()
        results_per_source = await asyncio.gather(*tasks)
        per_source_counts = {scraper_labels[i]: len(results_per_source[i]) for i in range(len(results_per_source))}
        logger.info("←← TW scrapers %.2fs — raw hits: %s", time.perf_counter() - t_all, per_source_counts)

    combined = [r for src in results_per_source for r in src]
    for listing in combined:
        if listing.data_source is None:
            listing.data_source = "scraped"
    await asyncio.sleep(settings.scraper_request_delay)

    combined = _filter_relevant(combined, keyword)
    combined = _dedup_cheapest_per_platform(combined)
    combined = _filter_outliers(combined, min_ratio=0.30)
    combined.sort(key=lambda l: l.price)

    if combined:
        logger.info(
            "TW final: %d listings for '%s' | platforms=%s | range=%.0f~%.0f TWD",
            len(combined), keyword, [l.platform for l in combined],
            combined[0].price, combined[-1].price,
        )
    else:
        logger.warning("TW final: 0 listings for '%s' (all scrapers empty after filters)", keyword)
    return combined


async def fetch_jp_prices(keyword: str, brand_platforms: list[str] | None = None) -> list[PriceListing]:
    """Return Japan listings from real e-commerce platforms only (no AI estimation).

    Priority for general platforms:
    1. Rakuten Ichiba API  (if RAKUTEN_APP_ID is set) → real product images
    2. Yahoo Shopping API  (if YAHOO_JP_APP_ID is set) → real product images
    3. HTML scrapers (Rakuten / Yahoo / Amazon / Kakaku)

    brand_platforms controls which brand-official stores to include:
    'uniqlo', 'gu', 'nike', 'adidas'. Pass [] or None to skip all brand stores.
    """
    brand_platforms = brand_platforms or []
    settings = get_settings()
    if settings.app_env != "production":
        logger.debug("DEV mock JP prices for '%s'", keyword)
        await asyncio.sleep(0.05)
        return _mock_jp_prices(keyword)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks: list = []
        scraper_labels: list[str] = []
        # SerpAPI Google Shopping works from any cloud IP — use as primary when key is set
        if settings.serpapi_key:
            scraper_labels.append("Google Shopping JP")
            tasks.append(_scrape_serpapi_jp(client, keyword, settings.serpapi_key))
        # Official free APIs (designed for server use, no IP blocking)
        if settings.rakuten_app_id:
            scraper_labels.append("楽天API")
            tasks.append(_scrape_rakuten_api(client, keyword, settings.rakuten_app_id, settings.rakuten_affiliate_id))
        else:
            scraper_labels.append("楽天HTML"); tasks.append(_scrape_rakuten_jp(client, keyword))

        if settings.yahoo_jp_app_id:
            scraper_labels.append("Yahoo JP API"); tasks.append(_scrape_yahoo_shopping_jp_api(client, keyword, settings.yahoo_jp_app_id))
        else:
            scraper_labels.append("Yahoo JP HTML"); tasks.append(_scrape_yahoo_shopping_jp(client, keyword))

        scraper_labels += ["Amazon JP", "Kakaku"]
        tasks += [
            _scrape_amazon_jp(client, keyword),
            _scrape_kakaku_jp(client, keyword),
        ]
        if "uniqlo" in brand_platforms:
            scraper_labels.append("UNIQLO JP"); tasks.append(_scrape_uniqlo_jp(client, keyword))
        if "gu" in brand_platforms:
            scraper_labels.append("GU JP"); tasks.append(_scrape_gu_jp(client, keyword))
        if "nike" in brand_platforms:
            scraper_labels.append("Nike JP"); tasks.append(_scrape_nike_jp(client, keyword))
        if "adidas" in brand_platforms:
            scraper_labels.append("Adidas JP"); tasks.append(_scrape_adidas_jp(client, keyword))
        logger.info("→→ JP scrapers (%d): %s", len(tasks), scraper_labels)
        t_all = time.perf_counter()
        results_per_source = await asyncio.gather(*tasks)
        per_source_counts = {scraper_labels[i]: len(results_per_source[i]) for i in range(len(results_per_source))}
        logger.info("←← JP scrapers %.2fs — raw hits: %s", time.perf_counter() - t_all, per_source_counts)

    combined = [r for src in results_per_source for r in src]
    for listing in combined:
        if listing.data_source is None:
            listing.data_source = "scraped"
    await asyncio.sleep(settings.scraper_request_delay)

    combined = _filter_relevant(combined, keyword)
    combined = _dedup_cheapest_per_platform(combined)
    combined = _filter_outliers(combined, min_ratio=0.30)
    combined.sort(key=lambda l: l.price)

    if combined:
        logger.info(
            "JP final: %d listings for '%s' | platforms=%s | range=%.0f~%.0f JPY",
            len(combined), keyword, [l.platform for l in combined],
            combined[0].price, combined[-1].price,
        )
    else:
        logger.warning("JP final: 0 listings for '%s' (all scrapers empty after filters)", keyword)
    return combined


async def enrich_listing_images(listings: list[PriceListing], max_lookup: int = 4) -> None:
    """Back-fill image_url for listings that have none.

    Uses Google Custom Search API when GOOGLE_API_KEY + GOOGLE_CSE_ID are set
    (higher quality), otherwise falls back to Bing.  Runs max_lookup concurrent
    lookups to add minimal latency (~1-2 s).
    """
    need = [l for l in listings if not l.image_url][:max_lookup]
    if not need:
        return

    settings = get_settings()
    use_google = bool(settings.google_api_key and settings.google_cse_id)

    async def _lookup(title: str) -> str | None:
        if settings.serpapi_key:
            result = await _serpapi_image_search(title[:80], settings.serpapi_key)
            if result:
                return result
        if use_google:
            result = await _google_image_search(title[:80], settings.google_api_key, settings.google_cse_id)
            if result:
                return result
        return await _bing_image_search(title[:80])

    imgs = await asyncio.gather(*[_lookup(l.title) for l in need], return_exceptions=True)
    enriched = 0
    for listing, img in zip(need, imgs):
        if isinstance(img, str) and img.startswith("https://"):
            listing.image_url = img
            enriched += 1
    logger.info(
        "Image enrichment (%s): filled %d/%d missing (total %d/%d)",
        "Google" if use_google else "Bing",
        enriched, len(need),
        sum(1 for l in listings if l.image_url), len(listings),
    )


async def _serpapi_image_search(keyword: str, api_key: str) -> str | None:
    """Google Images via SerpApi REST endpoint (no SDK needed).

    Free plan: 100 searches/month.  Set SERPAPI_KEY in Render env vars.
    Docs: https://serpapi.com/images-results
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_images",
                    "q": keyword,
                    "api_key": api_key,
                    "num": 5,
                    "safe": "active",
                    "hl": "zh-tw",
                },
                timeout=12,
            )
            if resp.status_code == 429:
                logger.warning("SerpApi rate limit reached")
                return None
            resp.raise_for_status()
            for item in resp.json().get("images_results", []):
                thumb = item.get("thumbnail") or item.get("original") or ""
                if thumb.startswith("https://"):
                    logger.info("SerpApi image for '%s': %s", keyword, thumb[:80])
                    return thumb
        return None
    except Exception as exc:
        logger.warning("SerpApi image search failed for '%s': %s", keyword, exc)
        return None


async def _google_image_search(keyword: str, api_key: str, cse_id: str) -> str | None:
    """Google Custom Search API – image search.

    Official API; returns high-quality product images.
    Free tier: 100 queries/day.  Requires:
      1. Create a Custom Search Engine at https://programmablesearch.google.com/
         (search entire web, enable "Image search" in Settings → Search features)
      2. Get an API key at https://console.developers.google.com/
      3. Set GOOGLE_API_KEY and GOOGLE_CSE_ID in Render env vars.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": api_key,
                    "cx": cse_id,
                    "q": keyword,
                    "searchType": "image",
                    "imgSize": "medium",
                    "imgType": "photo",
                    "num": 3,
                    "safe": "active",
                },
                timeout=10,
            )
            if resp.status_code == 429:
                logger.warning("Google CSE daily quota reached; falling back to Bing")
                return None
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                link = item.get("link", "")
                if link.startswith("https://"):
                    logger.info("Google image for '%s': %s", keyword, link[:80])
                    return link
        return None
    except Exception as exc:
        logger.warning("Google image search failed for '%s': %s", keyword, exc)
        return None


async def _bing_image_search(keyword: str) -> str | None:
    """Bing Image Search HTML – extract Bing CDN thumbnail from a.iusc JSON."""
    url = f"https://www.bing.com/images/search?q={quote(keyword + ' 商品')}&first=1&count=5&mkt=zh-TW&adlt=moderate"
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
            }, timeout=12)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Primary: a.iusc elements contain JSON with turl (Bing CDN thumbnail)
            for el in soup.select("a.iusc")[:8]:
                try:
                    data = json.loads(el.get("m", "{}"))
                    turl = data.get("turl", "")
                    if turl.startswith("https://tse"):
                        logger.info("Bing thumbnail for '%s': %s", keyword, turl[:80])
                        return turl
                except (json.JSONDecodeError, AttributeError):
                    continue

            # Secondary: img elements with src
            for img in soup.select("img.mimg[src]")[:5]:
                src = img.get("src", "")
                if src.startswith("https://"):
                    logger.info("Bing img fallback for '%s': %s", keyword, src[:80])
                    return src

        logger.debug("Bing: no thumbnail for '%s'", keyword)
        return None
    except Exception as exc:
        logger.warning("Bing image search failed for '%s': %s", keyword, exc)
        return None


async def _ddg_image_search(keyword: str) -> str | None:
    """DuckDuckGo image search – two-step vqd token + i.js JSON."""
    query = f"{keyword} 商品"
    headers = {"User-Agent": _UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            html_resp = await client.get(
                "https://duckduckgo.com/",
                params={"q": query, "iax": "images", "ia": "images"},
                headers={**headers, "Accept": "text/html"},
                timeout=10,
            )
            # DDG embeds vqd as vqd='...' or vqd="..." or vqd=1234-...
            vqd_match = (
                re.search(r'vqd=["\']?([\d][\d\-]+[\d])["\']?', html_resp.text)
                or re.search(r'"vqd":"([^"]+)"', html_resp.text)
            )
            if not vqd_match:
                logger.debug("DDG vqd not found for '%s'; status=%s", keyword, html_resp.status_code)
                return None
            vqd = vqd_match.group(1)

            json_resp = await client.get(
                "https://duckduckgo.com/i.js",
                params={"q": query, "vqd": vqd, "o": "json", "s": "0", "l": "wt-wt"},
                headers={**headers, "Referer": "https://duckduckgo.com/", "Accept": "application/json"},
                timeout=10,
            )
            results = json_resp.json().get("results", [])

        for item in results[:8]:
            thumb = item.get("thumbnail") or item.get("image") or ""
            if thumb.startswith("https://") and "bing.net" in thumb:
                return thumb
        for item in results[:8]:
            thumb = item.get("thumbnail") or item.get("image") or ""
            if thumb.startswith("https://"):
                return thumb
        return None
    except Exception as exc:
        logger.warning("DDG image search failed for '%s': %s", keyword, exc)
        return None


async def _wikipedia_image(keyword: str) -> str | None:
    """Wikipedia pageimages API – works well for famous consumer electronics."""
    # Try both English and Chinese Wikipedia
    for lang, title in [("en", keyword), ("zh", keyword)]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "titles": title,
                        "prop": "pageimages",
                        "pithumbsize": 300,
                        "format": "json",
                        "redirects": 1,
                    },
                    headers={"User-Agent": _UA},
                    timeout=8,
                )
                pages = resp.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    src = page.get("thumbnail", {}).get("source", "")
                    if src and src.startswith("https://"):
                        logger.info("Wikipedia image for '%s' (%s): %s", keyword, lang, src[:80])
                        return src
        except Exception as exc:
            logger.debug("Wikipedia image failed (%s) for '%s': %s", lang, keyword, exc)
    return None


async def fetch_product_thumbnail(keyword: str) -> str | None:
    """Return a product thumbnail URL.

    Priority:
    1. Google Custom Search API (if GOOGLE_API_KEY + GOOGLE_CSE_ID are set) –
       official API, highest quality, 100 free queries/day
    2. Bing Image Search HTML + DuckDuckGo + Wikipedia – concurrent, no key needed
    Returns None on total failure so it never blocks the main pipeline.
    """
    settings = get_settings()

    # Priority 1: SerpApi Google Images (100 free/month, best quality)
    if settings.serpapi_key:
        result = await _serpapi_image_search(keyword, settings.serpapi_key)
        if result:
            return result

    # Priority 2: Google Custom Search API (100 free/day)
    if settings.google_api_key and settings.google_cse_id:
        result = await _google_image_search(keyword, settings.google_api_key, settings.google_cse_id)
        if result:
            return result

    # Priority 3: Concurrent Bing / DDG / Wikipedia fallback (no key needed)
    results = await asyncio.gather(
        _bing_image_search(keyword),
        _ddg_image_search(keyword),
        _wikipedia_image(keyword),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, str) and r.startswith("https://"):
            logger.info("fetch_product_thumbnail '%s' → %s", keyword, r[:80])
            return r
    logger.warning("All image sources failed for '%s'", keyword)
    return None
