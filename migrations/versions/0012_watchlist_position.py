"""watchlist_position

Adds a nullable `position` ordering column to `watchlists` (issue #66). Lets a user
reorder their watchlists via `PATCH /api/v1/watchlists/reorder`; the list endpoint then
returns them ordered by `position ASC NULLS LAST, created_at ASC`, so lists that have
never been reordered (position `NULL`) fall back to creation order.

Nullable on purpose: existing rows keep `NULL` until the user reorders, and newly created
watchlists start `NULL` too — no backfill needed. The `watchlists` table already has
owner-only RLS (see 0001); this column inherits it unchanged.

Compliance note (HU3): `position` is a pure display-ordering integer. Like every other
column in this schema it is not a buy/sell/order/quantity/price_target field, and must
never become one — see the product's compliance stance.

Revision ID: 0012
Revises: 0011b
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
# Re-chained onto 0011b (issue #21): 0011b and 0012 both originally declared
# down_revision "0011", branching the tree into two heads and breaking
# `alembic upgrade head`. 0011b was the branch that actually shipped (the live
# DB is stamped at 0011b with `user_notes` present but `watchlists.position`
# absent), so slotting 0012 after 0011b linearizes the chain AND makes the one
# pending migration on existing environments the column this file adds — no
# `alembic stamp` needed. Matches the 0009 -> 0009b -> 0010 convention.
down_revision: str | None = "0011b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- watchlists.position — nullable display-ordering column (issue #66). NULL means
-- "never reordered": the list endpoint sorts those last, by created_at. Owner-only
-- RLS on `watchlists` (0001) already covers this column — nothing to add here.
-- =============================================================================
alter table public.watchlists
    add column if not exists position integer;
"""

_DOWNGRADE_SQL = """
alter table public.watchlists
    drop column if exists position;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
