"""Persist scenario specialist contributions and Midas consensus.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table public.scenarios
            add column if not exists agent_contributions jsonb not null default '[]'::jsonb,
            add column if not exists consensus jsonb;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        alter table public.scenarios
            drop column if exists consensus,
            drop column if exists agent_contributions;
        """
    )
