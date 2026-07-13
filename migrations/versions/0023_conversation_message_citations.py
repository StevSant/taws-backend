"""Persist structured citations produced by grounded chat turns.

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.conversation_messages
    add column if not exists citations jsonb;
"""

_DOWNGRADE_SQL = """
alter table public.conversation_messages
    drop column if exists citations;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
