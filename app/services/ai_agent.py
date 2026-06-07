"""
AI Agent – product identification & multilingual keyword mapping.

Handles both text queries and product image uploads. Uses Google Gemini's vision
capability for images and structured JSON output for parseable responses.
"""
from __future__ import annotations

import json
import logging
from typing import Union

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.schemas.product import KeywordMapping
from app.services.gemini_client import generate_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a multilingual product identification specialist.
Given a product name (in any language) or a product image, you identify the product,
then provide the optimal search keyword in Traditional Chinese for Taiwan e-commerce platforms
(momo, Shopee TW) and in Japanese for Japan e-commerce platforms (Amazon JP, Rakuten),
plus a concise product description in Traditional Chinese, and a list of brand-official
platforms whose dedicated store should be searched.

You must respond with a valid JSON object with this exact structure:
{
  "refined_tw_keyword": "優化後的繁體中文商品名稱",
  "refined_jp_keyword": "最適化された日本語商品名/型番",
  "category": "商品分類（繁體中文）",
  "product_description": "商品簡介（繁體中文，2-3句）：涵蓋主要規格、核心特色與適用場景。",
  "brand_platforms": []
}

brand_platforms rules:
- Only include brands whose OFFICIAL store sells this exact product type.
- Valid values: "nike", "adidas", "uniqlo", "gu"
- Use [] for products not sold by any of those brands (electronics, food, books, etc.)
- A product can have multiple brands only if it's a multi-brand collaboration.

Examples:
- For "Sony headphones": {
    "refined_tw_keyword": "Sony WH-1000XM5 無線降噪耳機",
    "refined_jp_keyword": "ソニー WH-1000XM5 ワイヤレスノイズキャンセリングヘッドホン",
    "category": "電子產品",
    "product_description": "Sony WH-1000XM5 搭載業界頂級主動降噪技術，有效屏蔽環境噪音。支援 Multipoint 雙裝置同時連線，並提供長達 30 小時的續航力，是商務出行與日常通勤的理想夥伴。",
    "brand_platforms": []
  }
- For "Nike Air Max 270": {
    "refined_tw_keyword": "Nike Air Max 270 男鞋",
    "refined_jp_keyword": "ナイキ エア マックス 270",
    "category": "運動鞋",
    "product_description": "Nike Air Max 270 搭載全掌式 Air 氣墊，提供卓越的緩震效果與舒適感。採用透氣網眼鞋面設計，適合日常穿搭與輕量運動，是時尚與機能兼具的經典鞋款。",
    "brand_platforms": ["nike"]
  }
- For "Adidas Ultraboost": {
    "refined_tw_keyword": "Adidas Ultraboost 跑鞋",
    "refined_jp_keyword": "アディダス ウルトラブースト",
    "category": "跑步鞋",
    "product_description": "Adidas Ultraboost 採用 Boost 中底技術，提供強勁的能量回彈，讓每一步都輕盈有力。Primeknit 鞋面貼合腳型，透氣舒適，適合長距離跑步與日常穿搭。",
    "brand_platforms": ["adidas"]
  }
- For "UNIQLO HEATTECH": {
    "refined_tw_keyword": "UNIQLO HEATTECH 保暖內衣",
    "refined_jp_keyword": "ユニクロ ヒートテック",
    "category": "服飾",
    "product_description": "UNIQLO HEATTECH 採用獨家發熱保暖技術，將身體散發的水蒸氣轉化為熱能，輕薄卻能有效鎖住體溫。貼身版型不影響外搭層次，是秋冬必備的保暖內著。",
    "brand_platforms": ["uniqlo"]
  }
- For a cosmetic product image: {
    "refined_tw_keyword": "資生堂極上御藏精華液",
    "refined_jp_keyword": "資生堂 アルティミューン パワライジング コンセントレート",
    "category": "美妝保養",
    "product_description": "資生堂極上御藏精華液採用獨家 ImuGeneration 技術，強化肌膚自我防禦機制，持續活化肌膚免疫力。質地清透不黏膩，適合各種膚質，長期使用可感受肌膚更亮澤有彈性。",
    "brand_platforms": []
  }

Always return valid JSON only, no additional text."""

_GENERATION_CONFIG = {
    "temperature": 0.2,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 4096,
}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10))
async def analyze_input(
    input_type: str,
    data: Union[str, bytes],
    media_type: str = "image/jpeg",
) -> KeywordMapping:
    """Identify a product from text or image and return bilingual search keywords.

    Args:
        input_type: ``"text"`` or ``"image"``.
        data: Raw UTF-8 query string, or image bytes.
        media_type: MIME type used only when ``input_type="image"``.

    Returns:
        A :class:`KeywordMapping` with TW keyword, JP keyword, and category.
    """
    settings = get_settings()

    if input_type == "text":
        if not isinstance(data, str):
            data = data.decode("utf-8")
        contents = f"{_SYSTEM_PROMPT}\n\nProduct query: {data}"
    elif input_type == "image":
        if isinstance(data, str):
            data = data.encode("utf-8")
        import io
        import PIL.Image
        image = PIL.Image.open(io.BytesIO(data))
        contents = [f"{_SYSTEM_PROMPT}\n\nPlease identify this product and return the JSON.", image]
    else:
        raise ValueError(f"Unsupported input_type '{input_type}'. Use 'text' or 'image'.")

    response, model_used = await generate_with_fallback(
        api_key=settings.gemini_api_key,
        contents=contents,
        generation_config=_GENERATION_CONFIG,
    )

    try:
        result_text = response.text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        result = json.loads(result_text)
        mapping = KeywordMapping(**result)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse Gemini response (model=%s): %s", model_used, response.text)
        raise RuntimeError(f"Gemini returned invalid JSON: {e}") from e

    logger.info(
        "Keyword mapping resolved via %s: TW=%s | JP=%s | category=%s",
        model_used,
        mapping.refined_tw_keyword,
        mapping.refined_jp_keyword,
        mapping.category,
    )
    return mapping
