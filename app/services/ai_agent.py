"""
AI Agent – product identification & multilingual keyword mapping.

Handles both text queries and product image uploads.  Uses Claude's vision
capability for images and structured tool-use to guarantee a parseable JSON
response every time.
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Union

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.schemas.product import KeywordMapping

logger = logging.getLogger(__name__)

# Reusable tool definition for structured output
_KEYWORD_TOOL: dict = {
    "name": "return_keyword_mapping",
    "description": (
        "Return the standardised product keywords for Taiwan and Japan "
        "e-commerce searches, plus a product category."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "refined_tw_keyword": {
                "type": "string",
                "description": "Standardised Traditional Chinese product name suitable for TW e-commerce search.",
            },
            "refined_jp_keyword": {
                "type": "string",
                "description": (
                    "Optimised Japanese product name / model number suitable for "
                    "Amazon JP or Rakuten search. Use katakana/kanji as appropriate."
                ),
            },
            "category": {
                "type": "string",
                "description": "Broad product category in Traditional Chinese (e.g. 電子產品, 美妝保養, 食品飲料).",
            },
        },
        "required": ["refined_tw_keyword", "refined_jp_keyword", "category"],
    },
}

_SYSTEM_PROMPT = (
    "You are a multilingual product identification specialist. "
    "Given a product name (in any language) or a product image, you identify the product, "
    "then provide the optimal search keyword in Traditional Chinese for Taiwan e-commerce platforms "
    "(momo, Shopee TW) and in Japanese for Japan e-commerce platforms (Amazon JP, Rakuten). "
    "Always call the `return_keyword_mapping` tool with your result."
)


def _build_text_message(query: str) -> list[dict]:
    return [{"role": "user", "content": query}]


def _build_image_message(image_bytes: bytes, media_type: str = "image/jpeg") -> list[dict]:
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64},
                },
                {
                    "type": "text",
                    "text": (
                        "Please identify this product and call the `return_keyword_mapping` tool "
                        "with the optimised search keywords."
                    ),
                },
            ],
        }
    ]


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
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    if input_type == "text":
        if not isinstance(data, str):
            data = data.decode("utf-8")
        messages = _build_text_message(
            f"Product query: {data}\n\nPlease call `return_keyword_mapping` with the result."
        )
    elif input_type == "image":
        if isinstance(data, str):
            data = data.encode("utf-8")
        messages = _build_image_message(data, media_type=media_type)
    else:
        raise ValueError(f"Unsupported input_type '{input_type}'. Use 'text' or 'image'.")

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        tools=[_KEYWORD_TOOL],
        tool_choice={"type": "tool", "name": "return_keyword_mapping"},
        messages=messages,
    )

    # Extract the forced tool call
    tool_use_block = next(
        (block for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_use_block is None:
        raise RuntimeError("Claude did not return a tool_use block as expected.")

    mapping = KeywordMapping(**tool_use_block.input)
    logger.info(
        "Keyword mapping resolved: TW=%s | JP=%s | category=%s",
        mapping.refined_tw_keyword,
        mapping.refined_jp_keyword,
        mapping.category,
    )
    return mapping
