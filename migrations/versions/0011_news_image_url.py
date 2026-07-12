"""news_items.image_url (article hero/thumbnail)

Adds optional image URL for news cards and detail views.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.news_items
    add column if not exists image_url text;
"""

_DOWNGRADE_SQL = """
alter table public.news_items
    drop column if exists image_url;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
