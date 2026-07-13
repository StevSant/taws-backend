"""news_items browse indexes

Indexes backing GET /api/v1/news/browse (issue #70): the published_at ordering and
recency cutoff every browse query applies, and a GIN index for the related_symbols
array-overlap filter used by the symbol / asset-class facets.

Migration 0009 already indexes (analysis_status, published_at desc), which only helps
queries that also constrain analysis_status — the browse default doesn't. The plain
published_at index covers the unfiltered case.

Source / provider / analysis_status are equality filters over low-cardinality columns;
at this corpus size a sequential scan beats an index lookup, so none is added.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
create index if not exists news_items_published_at_idx
    on public.news_items (published_at desc);

create index if not exists news_items_related_symbols_gin
    on public.news_items using gin (related_symbols);
"""

_DOWNGRADE_SQL = """
drop index if exists public.news_items_related_symbols_gin;
drop index if exists public.news_items_published_at_idx;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
