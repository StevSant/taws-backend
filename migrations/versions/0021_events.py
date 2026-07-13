"""events — durable storage for the Sentinel (Event Intelligence) pipeline

`MemoryEventRepository` was the ONLY implementation of `EventRepositoryPort`, and
`Container.get_event_repository()` returned it unconditionally — with no `app_env` gate
and no alternative adapter to swap to. So every Sentinel scan wrote its Gemini-enriched
events into a plain in-process `list[]` that died on restart.

That was not merely "state we lose on deploy": it broke a user-visible flow. A Telegram
event alert carries inline buttons whose callback data holds the event id;
`EventCallbackHandler` resolves that id through `event_repository.get(...)`. After any
restart — or simply from a second worker/replica, which never saw the write — that lookup
returns `None`, so the buttons on a still-visible Telegram message are permanently dead.
`GET /api/v1/event-intelligence/events` likewise returned different data per worker.

This table is the durable backing store. Events are SHARED/global market analysis, not
user-owned — same ownership model as `signals` (0001) and `sentiment_readings` (0015):
the pipeline writes them through the service-role key (which bypasses RLS), and any
authenticated user may read them.

The columns flatten `EnrichedEvent` and the `NewsEvent` it wraps into one row: the
original news fields carry an `original_` prefix, the Gemini analysis fields do not.
`affected_assets` / `affected_sectors` / `suggested_questions` are `text[]`, which
PostgREST returns natively as JSON arrays, so the row mapper needs no parsing step.

Compliance note (HU3, same stance as every other migration in this schema): an event is a
news/analysis record. There is no buy/sell/order/quantity/price_target column here, and
there must never be one — `suggested_questions` holds questions to ask the agent, never
actions to take.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-13

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- events — Gemini-enriched news events produced by the Sentinel pipeline.
-- Shared/global market analysis, NOT user-owned (same model as signals).
-- `id` is text: the pipeline mints it, and it is echoed back through Telegram
-- inline-button callback data, so it must round-trip exactly as produced.
-- =============================================================================
create table if not exists public.events (
    id text primary key,

    -- the original NewsEvent this was enriched from
    original_title text not null,
    original_description text not null,
    original_content text not null,
    original_source text not null,
    original_url text,
    original_published_at timestamptz,

    -- the Gemini analysis
    summary text not null,
    importance double precision not null,
    should_notify boolean not null,
    affected_assets text[] not null default '{}',
    affected_sectors text[] not null default '{}',
    confidence double precision not null,
    reasoning text not null,
    suggested_questions text[] not null default '{}',
    analyzed_at timestamptz not null,

    created_at timestamptz not null default now()
);

-- The events feed and the chat `get_recent_events` tool both read newest-first.
create index if not exists events_analyzed_at_idx on public.events (analyzed_at desc);

-- Broadcast selection filters on these two before ordering.
create index if not exists events_should_notify_importance_idx
    on public.events (should_notify, importance desc);

alter table public.events enable row level security;

-- Written by the Sentinel pipeline via the service-role key (which bypasses RLS);
-- readable by any authenticated user, like signals and sentiment_readings.
create policy "events_select_authenticated" on public.events
    for select using (auth.role() = 'authenticated');
"""

_DOWNGRADE_SQL = """
drop table if exists public.events cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
