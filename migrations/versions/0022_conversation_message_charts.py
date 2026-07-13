"""conversation_messages.charts — persist the charts an assistant turn drew

Adds a nullable `charts jsonb` column so a reopened thread re-renders the charts the user saw,
instead of dropping to a text-only transcript. Charts are produced by the agent's render tools
and streamed live over SSE (`ChartEvent`), but until now only the reply *text* was persisted —
so navigating away and back, or a full reload, lost every chart.

`charts` stores a JSON array of already-serialized ChartSpec wire dicts (the exact shape the
frontend consumes from the SSE `{"chart": {...}}` frame), so no re-mapping is needed on
rehydrate. It is written ONLY for assistant turns that drew something; user turns and text-only
replies leave it NULL.

Nullable with no default, on purpose:

  * `null` — the turn carried no chart (every row that predates this revision, and every
             text-only turn). Rendered as a plain message.
  * a JSON array — the charts to re-render, in arrival order.

A `NOT NULL DEFAULT '[]'` would add no information and force a rewrite of every existing row.
No check constraint: the payload is an opaque, evolving presentation artifact (chart types grow
over phases), validated by the frontend renderer, not the database — the same posture the
`entities`/`related_symbols` JSON columns on `news_items` take.

Compliance note (HU3): a chart is descriptive market data (prices, deltas, volatility). It
carries no buy/sell/order/quantity/price_target semantics, and must never be extended to.

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
alter table public.conversation_messages
    add column if not exists charts jsonb;
"""

_DOWNGRADE_SQL = """
alter table public.conversation_messages
    drop column if exists charts;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
