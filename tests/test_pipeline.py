"""
Unit & integration tests for the core pipeline.

Run with: pytest tests/ -v
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.product import KeywordMapping, PriceListing, BuyingAdvice, ProsCons
from app.services.scraper import _mock_tw_prices, _mock_jp_prices, fetch_tw_prices, fetch_jp_prices


# ────────────────────────────────────────────────────────────────────────────
# Scraper
# ────────────────────────────────────────────────────────────────────────────

def test_mock_tw_prices_returns_three_listings():
    listings = _mock_tw_prices("Sony WH-1000XM5")
    assert len(listings) == 3
    for l in listings:
        assert l.currency == "TWD"
        assert l.price > 0


def test_mock_jp_prices_returns_three_listings():
    listings = _mock_jp_prices("ソニー WH-1000XM5")
    assert len(listings) == 3
    for l in listings:
        assert l.currency == "JPY"
        assert l.price > 0


def test_mock_prices_deterministic():
    """Same keyword must always return the same prices (for stable caching)."""
    kw = "Nintendo Switch"
    a = _mock_tw_prices(kw)
    b = _mock_tw_prices(kw)
    assert [l.price for l in a] == [l.price for l in b]


@pytest.mark.asyncio
async def test_fetch_tw_prices_development_mode(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    from app.core.config import get_settings
    get_settings.cache_clear()
    listings = await fetch_tw_prices("iPhone 16")
    assert len(listings) >= 1
    assert all(l.currency == "TWD" for l in listings)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_fetch_jp_prices_development_mode(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    from app.core.config import get_settings
    get_settings.cache_clear()
    listings = await fetch_jp_prices("iPhone 16")
    assert len(listings) >= 1
    assert all(l.currency == "JPY" for l in listings)
    get_settings.cache_clear()


# ────────────────────────────────────────────────────────────────────────────
# AI Agent (mocked Anthropic client)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_input_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from app.core.config import get_settings
    get_settings.cache_clear()

    fake_tool_block = MagicMock()
    fake_tool_block.type = "tool_use"
    fake_tool_block.input = {
        "refined_tw_keyword": "Sony WH-1000XM5 無線降噪耳機",
        "refined_jp_keyword": "ソニー WH-1000XM5 ワイヤレスノイズキャンセリングヘッドホン",
        "category": "電子產品",
    }
    fake_response = MagicMock()
    fake_response.content = [fake_tool_block]

    with patch("app.services.ai_agent.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=fake_response)
        mock_cls.return_value = mock_client

        from app.services.ai_agent import analyze_input
        result = await analyze_input("text", "Sony WH-1000XM5")

    assert isinstance(result, KeywordMapping)
    assert "Sony" in result.refined_tw_keyword
    assert result.category == "電子產品"
    get_settings.cache_clear()


# ────────────────────────────────────────────────────────────────────────────
# Advisor (mocked Anthropic client)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_buying_advice(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from app.core.config import get_settings
    get_settings.cache_clear()

    tw = _mock_tw_prices("Nintendo Switch")
    jp = _mock_jp_prices("ニンテンドースイッチ")

    fake_tool_block = MagicMock()
    fake_tool_block.type = "tool_use"
    fake_tool_block.input = {
        "price_comparison_summary": "台灣平均價格約為 NT$8,500，日本退稅後約 NT$7,800。",
        "best_deal_location": "Japan",
        "pros_cons": {
            "pros": ["日本有退稅優惠", "價格較低"],
            "cons": ["需加計運費", "保固在台灣使用可能有問題"],
        },
        "verdict": "建議在日本購買，退稅後約省 NT$700。",
    }
    fake_response = MagicMock()
    fake_response.content = [fake_tool_block]

    with patch("app.services.advisor.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=fake_response)
        mock_cls.return_value = mock_client

        from app.services.advisor import generate_buying_advice
        advice, rate = await generate_buying_advice(tw, jp, current_exchange_rate=0.218)

    assert isinstance(advice, BuyingAdvice)
    assert advice.best_deal_location == "Japan"
    assert rate == 0.218
    assert advice.tw_average_price_twd is not None
    get_settings.cache_clear()


# ────────────────────────────────────────────────────────────────────────────
# FastAPI endpoint smoke test
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_endpoint_text(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("APP_ENV", "development")
    from app.core.config import get_settings
    get_settings.cache_clear()

    mapping = KeywordMapping(
        refined_tw_keyword="Sony WH-1000XM5",
        refined_jp_keyword="ソニー WH-1000XM5",
        category="電子產品",
    )
    tw = _mock_tw_prices("Sony WH-1000XM5")
    jp = _mock_jp_prices("ソニー WH-1000XM5")
    advice = BuyingAdvice(
        price_comparison_summary="台灣較便宜。",
        best_deal_location="Taiwan",
        tw_average_price_twd=9000.0,
        jp_average_price_twd=10500.0,
        jp_tax_free_price_twd=9450.0,
        pros_cons=ProsCons(pros=["本地保固"], cons=["無退稅"]),
        verdict="建議在台灣購買。",
    )

    from httpx import AsyncClient, ASGITransport

    with (
        patch("app.api.routes.analyze_input", AsyncMock(return_value=mapping)),
        patch("app.api.routes.fetch_tw_prices", AsyncMock(return_value=tw)),
        patch("app.api.routes.fetch_jp_prices", AsyncMock(return_value=jp)),
        patch("app.api.routes.generate_buying_advice", AsyncMock(return_value=(advice, 0.218))),
        patch("app.api.routes.get_session") as mock_ctx,
    ):
        # Make get_session a no-op async context manager
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        mock_session.flush = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        from main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/search", data={"query": "Sony WH-1000XM5"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["advice"]["best_deal_location"] == "Taiwan"
    assert "tw_listings" in body
    get_settings.cache_clear()
