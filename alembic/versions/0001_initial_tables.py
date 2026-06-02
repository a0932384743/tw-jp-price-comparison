"""initial tables

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("input_type", sa.String(10), nullable=False),
        sa.Column("raw_query", sa.Text(), nullable=True),
        sa.Column("image_filename", sa.String(255), nullable=True),
        sa.Column("refined_tw_keyword", sa.String(255), nullable=False),
        sa.Column("refined_jp_keyword", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("exchange_rate_jpy_twd", sa.Float(), nullable=False),
        sa.Column("best_deal_location", sa.String(20), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
    )

    op.create_table(
        "price_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "search_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("search_history.id"),
            nullable=True,
        ),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("market", sa.String(5), nullable=False),
        sa.Column("platform", sa.String(100), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("cache_date", sa.Date(), nullable=False),
        sa.UniqueConstraint("keyword", "platform", "cache_date", name="uq_cache_per_day"),
    )
    op.create_index("ix_price_cache_keyword", "price_cache", ["keyword"])
    op.create_index("ix_price_cache_cache_date", "price_cache", ["cache_date"])


def downgrade() -> None:
    op.drop_index("ix_price_cache_cache_date", table_name="price_cache")
    op.drop_index("ix_price_cache_keyword", table_name="price_cache")
    op.drop_table("price_cache")
    op.drop_table("search_history")
