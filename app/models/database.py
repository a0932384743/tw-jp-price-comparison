"""
SQLAlchemy async models.

Two tables:
  - search_history  : every user search (text or image)
  - price_cache     : de-duplicated listings keyed by (keyword, platform, date)

The cache table lets you skip live scraping for popular keywords fetched
within the same day, reducing platform scraping load significantly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Raw user input
    input_type = Column(String(10), nullable=False)          # "text" | "image"
    raw_query = Column(Text, nullable=True)                  # present for text searches
    image_filename = Column(String(255), nullable=True)      # present for image searches

    # AI-resolved keywords
    refined_tw_keyword = Column(String(255), nullable=False)
    refined_jp_keyword = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)

    # Exchange rate at time of search
    exchange_rate_jpy_twd = Column(Float, nullable=False)

    # Advisor output snapshot
    best_deal_location = Column(String(20), nullable=True)
    verdict = Column(Text, nullable=True)

    listings = relationship("PriceCache", back_populates="search", cascade="all, delete-orphan")


class PriceCache(Base):
    """Cached price listing.  One row per (keyword, platform, cache_date)."""

    __tablename__ = "price_cache"
    __table_args__ = (
        UniqueConstraint("keyword", "platform", "cache_date", name="uq_cache_per_day"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    search_id = Column(UUID(as_uuid=True), ForeignKey("search_history.id"), nullable=True)

    keyword = Column(String(255), nullable=False, index=True)
    market = Column(String(5), nullable=False)               # "TW" | "JP"
    platform = Column(String(100), nullable=False)
    title = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String(5), nullable=False)
    url = Column(Text, nullable=False)
    cache_date = Column(Date, nullable=False, default=date.today, index=True)

    search = relationship("SearchHistory", back_populates="listings")
