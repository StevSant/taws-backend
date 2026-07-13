"""merge_heads

Both `0011b` (user_notes) and `0012` (watchlist_position) set `down_revision = "0011"`
(news_image_url), which left the migration tree with two divergent heads. With two heads,
`alembic upgrade head` errors with "Multiple head revisions are present" and the
`test_migration_tree_has_single_head` guard fails.

This is a no-op merge revision: it creates no schema and runs no SQL. The user-notes table
(0011b) and the `watchlists.position` column (0012) are independent and already applied by
their own revisions — this revision only records that both are now ancestors of a single
tip, re-joining the branches so the chain terminates in exactly one head again.

Revision ID: 0013
Revises: 0011b, 0012
Create Date: 2026-07-12

"""

from collections.abc import Sequence

revision: str = "0013"
down_revision: tuple[str, ...] = ("0011b", "0012")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: this revision only re-joins two divergent migration heads."""


def downgrade() -> None:
    """No-op: reverting this merge splits the tree back into two heads."""
