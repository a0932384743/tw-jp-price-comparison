"""
Shared Gemini client with automatic model fallback on quota / rate-limit errors.

Priority order is based on available RPD (requests per day) from the dashboard:
  1. gemini-3.1-flash-lite  — 15 RPM, 500 RPD  (most headroom)
  2. gemini-2.5-flash-lite  — 10 RPM,  20 RPD
  3. gemini-3.5-flash       —  5 RPM,  20 RPD
  4. gemini-3-flash         —  5 RPM,  20 RPD
  5. gemini-2.5-flash       —  5 RPM,  20 RPD
"""
from __future__ import annotations

import logging
from typing import Any

import google.api_core.exceptions
import google.generativeai as genai

logger = logging.getLogger(__name__)

FALLBACK_MODELS: list[str] = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
]


async def generate_with_fallback(
    api_key: str,
    contents: Any,
    generation_config: dict,
) -> tuple[genai.types.GenerateContentResponse, str]:
    """Call Gemini, trying each model in FALLBACK_MODELS order.

    Falls back to the next model only on ResourceExhausted (429/quota).
    All other exceptions propagate immediately.

    Returns:
        (response, model_name_used)
    """
    genai.configure(api_key=api_key)

    last_quota_exc: Exception | None = None
    for model_name in FALLBACK_MODELS:
        try:
            logger.info("Gemini request using model: %s", model_name)
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config,
            )
            response = await model.generate_content_async(contents)
            logger.info("Gemini success with model: %s", model_name)
            return response, model_name
        except google.api_core.exceptions.ResourceExhausted as exc:
            logger.warning(
                "Model %s quota/rate-limit exceeded, falling back. Reason: %s",
                model_name,
                exc,
            )
            last_quota_exc = exc
        # Any other exception (invalid input, network error, etc.) propagates up.

    raise RuntimeError(
        "所有 Gemini 模型配額已用盡，請稍後再試。"
    ) from last_quota_exc
