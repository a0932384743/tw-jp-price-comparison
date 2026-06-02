"""
AI Advisor – cross-market purchasing analysis powered by Google Gemini.

Takes aggregated price data from both markets, applies the exchange rate and
Japan's 10 % tax-free refund, then asks Gemini to produce a structured
buying recommendation via JSON output.
"""
from __future__ import annotations

import json
import logging
import statistics

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.schemas.product import BuyingAdvice, PriceListing, ProsCons
from app.services.gemini_client import generate_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a savvy cross-border shopping advisor for Taiwanese consumers.
You always respond in Traditional Chinese.
Given price data from Taiwan and Japan, you calculate the real cost including
Japan's 10% consumption-tax refund for foreign visitors shopping in physical stores,
and you advise where the consumer will get the best deal.
Be concise, practical, and specific about savings amounts.

You must respond with a valid JSON object with this exact structure:
{
  "price_comparison_summary": "2-3 sentence narrative comparing TW and JP prices",
  "best_deal_location": "Taiwan" or "Japan" or "Similar",
  "pros_cons": {
    "pros": ["advantage 1", "advantage 2"],
    "cons": ["disadvantage 1", "disadvantage 2"]
  },
  "verdict": "One actionable recommendation sentence"
}

Always return valid JSON only, no additional text."""

_GENERATION_CONFIG = {
    "temperature": 0.3,
    "top_p": 0.9,
    "top_k": 40,
    "max_output_tokens": 1024,
}


def _average_price(listings: list[PriceListing]) -> float | None:
    prices = [l.price for l in listings if l.price > 0]
    return statistics.mean(prices) if prices else None


def _fmt(value: float | None, prefix: str = "", suffix: str = "") -> str:
    return f"{prefix}{value:,.0f}{suffix}" if value is not None else "(無資料)"


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
台灣平均價: {_fmt(tw_avg, "NT$")}

【日本商品價格 (JPY → TWD，匯率 1 JPY = {rate} TWD)】
{jp_block or '  (無資料)'}
日本平均價 (含稅): {_fmt(jp_avg_jpy, "¥")} ≈ {_fmt(jp_avg_twd, "NT$")}
日本平均價 (退稅 {int(tax_free_rate * 100)}%): {_fmt(jp_tax_free_twd, "≈ NT$")}

注意事項：
- 退稅優惠僅適用於在日本實體門市購買，線上購買無法退稅。
- 日本購買需加計國際運費（約 NT$300–800 / 件）或親自帶回的行李費用。
- 台灣商品享有本地保固，日本商品可能需要平行輸入報修。

請給出具體、精確的建議，並以 JSON 格式回傳。
""".strip()


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10))
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

    prompt = _SYSTEM_PROMPT + "\n\n" + _build_prompt(
        tw_prices, jp_prices, rate, settings.jp_tax_free_rate,
        tw_avg, jp_avg_jpy, jp_avg_twd, jp_tax_free_twd,
    )

    response, model_used = await generate_with_fallback(
        api_key=settings.gemini_api_key,
        contents=prompt,
        generation_config=_GENERATION_CONFIG,
    )

    try:
        result_text = response.text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        raw = json.loads(result_text)
        advice = BuyingAdvice(
            price_comparison_summary=raw["price_comparison_summary"],
            best_deal_location=raw["best_deal_location"],
            tw_average_price_twd=tw_avg,
            jp_average_price_twd=jp_avg_twd,
            jp_tax_free_price_twd=jp_tax_free_twd,
            pros_cons=ProsCons(**raw["pros_cons"]),
            verdict=raw["verdict"],
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error("Failed to parse Gemini response (model=%s): %s", model_used, response.text)
        raise RuntimeError(f"Gemini returned invalid JSON: {e}") from e

    logger.info("Advice generated via %s: best_deal=%s", model_used, advice.best_deal_location)
    return advice, rate
