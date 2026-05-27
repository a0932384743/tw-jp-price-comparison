"""
AI Agent – product identification & multilingual keyword mapping.

Handles both text queries and product image uploads. Uses Google Gemini's vision
capability for images and structured JSON output for parseable responses.
"""
from __future__ import annotations

import json
import logging
from typing import Union

import google.generativeai as genai
import google.api_core.exceptions
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.schemas.product import KeywordMapping

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a multilingual product identification specialist.
Given a product name (in any language) or a product image, you identify the product,
then provide the optimal search keyword in Traditional Chinese for Taiwan e-commerce platforms
(momo, Shopee TW) and in Japanese for Japan e-commerce platforms (Amazon JP, Rakuten).

You must respond with a valid JSON object with this exact structure:
{
  "refined_tw_keyword": "優化後的繁體中文商品名稱",
  "refined_jp_keyword": "最適化された日本語商品名/型番",
  "category": "商品分類（繁體中文）"
}

Examples:
- For "Sony headphones": {"refined_tw_keyword": "Sony WH-1000XM5 無線降噪耳機", "refined_jp_keyword": "ソニー WH-1000XM5 ワイヤレスノイズキャンセリングヘッドホン", "category": "電子產品"}
- For a cosmetic product image: {"refined_tw_keyword": "資生堂極上御藏精華液", "refined_jp_keyword": "資生堂 アルティミューン パワライジング コンセントレート", "category": "美妝保養"}

Always return valid JSON only, no additional text."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
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
    genai.configure(api_key=settings.gemini_api_key)

    # Use models/gemini-2.5-pro (latest stable multimodal model)
    model = genai.GenerativeModel(
        model_name="models/gemini-2.5-pro",
        generation_config={
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 4096,  # 建議根據實際需求設置，65536 太大容易超額
        },
    )

    if input_type == "text":
        if not isinstance(data, str):
            data = data.decode("utf-8")
        prompt = f"{_SYSTEM_PROMPT}\n\nProduct query: {data}"
        response = await model.generate_content_async(prompt)
    elif input_type == "image":
        if isinstance(data, str):
            data = data.encode("utf-8")

        # Gemini expects image as PIL Image or dict with inline_data
        import PIL.Image
        import io
        image = PIL.Image.open(io.BytesIO(data))

        prompt = f"{_SYSTEM_PROMPT}\n\nPlease identify this product and return the JSON."
        response = await model.generate_content_async([prompt, image])
    else:
        raise ValueError(f"Unsupported input_type '{input_type}'. Use 'text' or 'image'.")

    # Parse JSON response
    try:
        result_text = response.text.strip()
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        result = json.loads(result_text)
        mapping = KeywordMapping(**result)
    except google.api_core.exceptions.ResourceExhausted as e:
        logger.error("Gemini API quota exceeded: %s", str(e))
        raise RuntimeError("Gemini API 配額已用盡，請稍後再試或升級帳號。\n詳情請見 https://ai.google.dev/gemini-api/docs/rate-limits") from e
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse Gemini response: %s", response.text)
        raise RuntimeError(f"Gemini returned invalid JSON: {e}") from e

    logger.info(
        "Keyword mapping resolved: TW=%s | JP=%s | category=%s",
        mapping.refined_tw_keyword,
        mapping.refined_jp_keyword,
        mapping.category,
    )
    return mapping
