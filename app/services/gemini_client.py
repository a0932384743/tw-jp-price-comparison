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

# Models known to support Google Search grounding (try in order)
_GROUNDING_MODELS: list[str] = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
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


async def search_with_grounding(api_key: str, prompt: str) -> str | None:
    """Call Gemini with Google Search grounding enabled.

    Uses google_search_retrieval so Gemini queries Google live and grounds
    its answer in real search results — bypassing cloud-IP blocks on retail sites.

    Returns the raw text response, or None if all attempts fail.
    """
    genai.configure(api_key=api_key)

    try:
        search_tool = genai.protos.Tool(
            google_search_retrieval=genai.protos.GoogleSearchRetrieval()
        )
    except AttributeError:
        logger.warning("google_search_retrieval not available in this API version")
        return None

    for model_name in _GROUNDING_MODELS:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                tools=[search_tool],
                generation_config={"temperature": 0.1, "max_output_tokens": 2048},
            )
            response = await model.generate_content_async(prompt)
            logger.info("Grounded search success with model: %s", model_name)
            return response.text
        except google.api_core.exceptions.ResourceExhausted:
            continue
        except google.api_core.exceptions.InvalidArgument as exc:
            logger.debug("Model %s does not support grounding: %s", model_name, exc)
            continue
        except Exception as exc:
            logger.warning("Grounded search failed with %s: %s", model_name, exc)
            continue

    return None
