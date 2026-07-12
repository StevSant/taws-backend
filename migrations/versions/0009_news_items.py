"""news_items (persisted news + Analyst analysis_status)

Track-5 data layer: `news_items` — persists every news article the backend has ever
fetched from a `NewsProvider` (issue #1 — "News items are never persisted, no
analysis-status field exists"). Previously `GET /api/v1/news` fetched live on every
request and never wrote anything down, so there was no queryable, stable concept of
"has this specific article been analyzed yet" independent of whether some *other*
article about the same instrument already produced a `Signal`.

Includes `provider` (the fetching adapter's own identity, e.g. `"finnhub"`/`"marketaux"`,
distinct from `source`'s publisher name) since `NewsItem.provider` (issue #5) landed on
`main` before this migration merged — kept in the same revision rather than a follow-up
one, since this table has not shipped to any real database yet.

Backs the `NewsItemRepository` port
(`src/app/infrastructure/persistence/supabase_news_item_repository.py`), written by
`IngestNews` (persist-then-read behind `GET /api/v1/news`) and read/written by
`AnalyzePendingNews` (the batch analysis pipeline, issue #2/#3 —
`POST /api/v1/news/analyze-pending`).

Ownership note: UNLIKE `watchlists`/`review_states`, `news_items` is NOT user-owned —
it's the same instrument/market-wide data everyone sees, exactly like `signals`
(migration 0001). Same rationale as that table's comment: RLS is enabled as
defense-in-depth (in case a client ever queries Supabase directly with a user JWT
instead of only through this backend), but the only policy is a read policy for any
authenticated user — the backend itself always writes via the service-role key, which
bypasses RLS.

`analysis_status` is a plain `text` column (not a Postgres enum) constrained via
`check`, same "app-layer enum, DB-layer check constraint" choice `review_states.state`
(migration 0002) and `scenario_monitors.status` (migration 0008) make — adding a status
later is a one-line `check` change, not an `ALTER TYPE`. `signal_id` is a nullable FK to
`signals.id` (`on delete set null`, so deleting a signal never cascades into deleting the
news items that produced it) — set once `AnalyzePendingNews`/`GenerateSignal` finishes
classifying an item.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- news_items — every article ever fetched from a NewsProvider, deduped by url,
-- with a queryable, per-article analysis_status (issue #1).
-- =============================================================================
create table if not exists public.news_items (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    summary text not null,
    url text not null unique,
    source text not null,
    provider text not null,
    published_at timestamptz not null,
    related_symbols text[] not null default '{}',
    entities jsonb not null default '[]'::jsonb,
    sentiment_score numeric,
    analysis_status text not null default 'pending'
        check (analysis_status in ('pending', 'analyzed', 'skipped')),
    signal_id uuid references public.signals (id) on delete set null,
    created_at timestamptz not null default now()
);

-- `list_pending` (AnalyzePendingNews) filters on analysis_status and orders by
-- published_at; this composite index covers both in one scan.
create index if not exists news_items_pending_idx
    on public.news_items (analysis_status, published_at desc);

create index if not exists news_items_signal_id_idx on public.news_items (signal_id);

alter table public.news_items enable row level security;

-- Same visibility model as `signals` (migration 0001): shared reference data, written
-- by the backend via the service-role key (bypasses RLS); read-only for authenticated
-- users as defense-in-depth against a client ever querying Supabase directly.
create policy "news_items_select_authenticated" on public.news_items
    for select using (auth.role() = 'authenticated');
"""

_DOWNGRADE_SQL = """
drop table if exists public.news_items cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
