"""watchlist_items.symbol index — back the reverse "who tracks this symbol" lookup.

The hybrid Sentinel alert routing (`BroadcastImportantEvents`) added a reverse lookup —
`WatchlistRepository.list_user_ids_tracking(symbols)` — that filters `watchlist_items` by
`symbol` to find every user tracking an event's affected assets. Until now `watchlist_items`
was only indexed on `watchlist_id` (the forward "items in this watchlist" direction, 0001), so
that reverse filter was a full table scan on every scheduled scan tick. This adds the matching
`symbol` index.

Pure performance/index change: no column, constraint, RLS, or data change, so it is safe to
apply and to roll back at any time. `if not exists` / `if exists` keep it idempotent.

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-17

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
create index if not exists watchlist_items_symbol_idx
    on public.watchlist_items (symbol);
"""

_DOWNGRADE_SQL = """
drop index if exists watchlist_items_symbol_idx;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
