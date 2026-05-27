"""
AI Advisor – cross-market purchasing analysis powered by Claude.

Takes aggregated price data from both markets, applies the exchange rate and
Japan's 10 % tax-free refund, then asks Claude to produce a structured
buying recommendation via forced tool-use (guaranteed parseable output).
"""
from __future__ import annotations

import logging
import statistics

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.schemas.product import BuyingAdvice, PriceListing, ProsCons

logger = logging.getLogger(__name__)

_ADVICE_TOOL: dict = {
    "name": "return_buying_advice",
    "description": "Return a structured cross-market purchasing analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "price_comparison_summary": {
                "type": "string",
                "description": (
                    "2-3 sentence narrative comparing TW and JP prices, "
                    "mentioning the converted JPY prices in TWD."
                ),
            },
            "best_deal_location": {
                "type": "string",
                "enum": ["Taiwan", "Japan", "Similar"],
                "description": "Which market offers the better overall deal.",
            },
            "pros_cons": {
                "type": "object",
                "properties": {
                    "pros": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Advantages of buying in the best-deal location.",
                    },
                    "cons": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Disadvantages or caveats.",
                    },
                },
                "required": ["pros", "cons"],
            },
            "verdict": {
                "type": "string",
                "description": (
                    "One actionable recommendation sentence. E.g. "
                    "'Buy on momo – you save ~NT$600 vs Japan after shipping.' "
                    "or 'Buy in Japan for ~15% savings if you can tax-free shop.'"
                ),
            },
        },
        "required": [
            "price_comparison_summary",
            "best_deal_location",
            "pros_cons",
            "verdict",
        ],
    },
}

_SYSTEM_PROMPT = (
    "You are a savvy cross-border shopping advisor for Taiwanese consumers. "
    "You always respond in Traditional Chinese. "
    "Given price data from Taiwan and Japan, you calculate the real cost including "
    "Japan's 10% consumption-tax refund for foreign visitors shopping in physical stores, "
    "and you advise where the consumer will get the best deal. "
    "Be concise, practical, and specific about savings amounts. "
    "Always call the `return_buying_advice` tool with your result."
)


def _average_price(listings: list[PriceListing]) -> float | None:
    prices = [l.price for l in listings if l.price > 0]
    return statistics.mean(prices) if prices else None


def _build_prompt(
    tw_listings: list[PriceListing],
    jp_listings: list[PriceListing],
    rate: float,
    tax_free_rate: float,
    tw_avg: float | None,
    jp_avg_jpy: float | None,
    jp_avg_twd: float | None,
    jp_tax_free_twd: float | None,
) -> str:
    tw_block = "\n".join(
        f"  - {l.platform}: {l.title} – NT${l.price:,.0f}" for l in tw_listings
    )
    jp_block = "\n".join(
        f"  - {l.platform}: {l.title} – ¥{l.price:,.0f} (≈ NT${l.price * rate:,.0f})"
        for l in jp_listings
    )

    return f"""
以下是比價資料，請協助分析：

【台灣商品價格 (TWD)】
{tw_block or '  (無資料)'}
台灣平均價: NT${tw_avg:,.0f} if tw_avg else '(無資料)'

【日本商品價格 (JPY → TWD，匯率 1 JPY = {rate} TWD)】
{jp_block or '  (無資料)'}
日本平均價 (含稅): ¥{jp_avg_jpy:,.0f} ≈ NT${jp_avg_twd:,.0f} if jp_avg_jpy else '(無資料)'
日本平均價 (退稅 {int(tax_free_rate * 100)}%): ≈ NT${jp_tax_free_twd:,.0f} if jp_tax_free_twd else '(無資料)'

注意事項：
- 退稅優惠僅適用於在日本實體門市購買，線上購買無法退稅。
- 日本購買需加計國際運費（約 NT$300–800 / 件）或親自帶回的行李費用。
- 台灣商品享有本地保固，日本商品可能需要平行輸入報修。

請呼叫 `return_buying_advice` 工具，給出具體、精確的建議。
""".strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_buying_advice(
    tw_prices: list[PriceListing],
    jp_prices: list[PriceListing],
    current_exchange_rate: float | None = None,
) -> tuple[BuyingAdvice, float]:
    """Generate AI-powered buying advice comparing TW and JP prices.

    Args:
        tw_prices: Taiwan price listings (currency: TWD).
        jp_prices: Japan price listings (currency: JPY).
        current_exchange_rate: JPY→TWD rate. Falls back to config value if None.

    Returns:
        A tuple of (:class:`BuyingAdvice`, exchange_rate_used).
    """
    settings = get_settings()
    rate = current_exchange_rate if current_exchange_rate is not None else settings.jpy_to_twd_rate

    tw_avg = _average_price(tw_prices)
    jp_avg_jpy = _average_price(jp_prices)
    jp_avg_twd = jp_avg_jpy * rate if jp_avg_jpy is not None else None
    jp_tax_free_twd = jp_avg_twd * (1 - settings.jp_tax_free_rate) if jp_avg_twd is not None else None

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = _build_prompt(
        tw_prices, jp_prices, rate, settings.jp_tax_free_rate,
        tw_avg, jp_avg_jpy, jp_avg_twd, jp_tax_free_twd,
    )

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[_ADVICE_TOOL],
        tool_choice={"type": "tool", "name": "return_buying_advice"},
        messages=[{"role": "user", "content": prompt}],
    )

    tool_use_block = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_use_block is None:
        raise RuntimeError("Claude did not return a tool_use block as expected.")

    raw = tool_use_block.input
    advice = BuyingAdvice(
        price_comparison_summary=raw["price_comparison_summary"],
        best_deal_location=raw["best_deal_location"],
        tw_average_price_twd=tw_avg,
        jp_average_price_twd=jp_avg_twd,
        jp_tax_free_price_twd=jp_tax_free_twd,
        pros_cons=ProsCons(**raw["pros_cons"]),
        verdict=raw["verdict"],
    )

    logger.info("Advice generated: best_deal=%s", advice.best_deal_location)
    return advice, rate
