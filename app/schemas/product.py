"""Pydantic schemas shared across API request/response boundaries."""
from __future__ import annotations
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional


# --------------------------------------------------------------------------- #
# AI agent output
# --------------------------------------------------------------------------- #

class KeywordMapping(BaseModel):
    refined_tw_keyword: str = Field(description="Standardised Traditional Chinese product name")
    refined_jp_keyword: str = Field(description="Optimised Japanese product name / model number")
    category: str = Field(description="Product category (e.g. 電子產品, 美妝, 食品)")


# --------------------------------------------------------------------------- #
# Scraper output
# --------------------------------------------------------------------------- #

class PriceListing(BaseModel):
    platform: str
    title: str
    price: float = Field(description="Price in local currency (TWD or JPY)")
    currency: str = Field(default="TWD")
    url: str
    image_url: Optional[str] = Field(default=None, description="Product thumbnail URL")


# --------------------------------------------------------------------------- #
# Advisor output
# --------------------------------------------------------------------------- #

class ProsCons(BaseModel):
    pros: list[str]
    cons: list[str]


class BuyingAdvice(BaseModel):
    price_comparison_summary: str
    best_deal_location: str = Field(description="'Taiwan' | 'Japan' | 'Similar'")
    tw_average_price_twd: Optional[float] = None
    jp_average_price_twd: Optional[float] = None
    jp_tax_free_price_twd: Optional[float] = None
    pros_cons: ProsCons
    verdict: str


# --------------------------------------------------------------------------- #
# API response envelope
# --------------------------------------------------------------------------- #

class SearchResponse(BaseModel):
    keyword_mapping: KeywordMapping
    tw_listings: list[PriceListing]
    jp_listings: list[PriceListing]
    exchange_rate_jpy_twd: float
    advice: BuyingAdvice
