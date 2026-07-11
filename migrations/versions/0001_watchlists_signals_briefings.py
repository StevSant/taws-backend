"""watchlists, signals, briefings, review_states

Track-5 T0 data layer: watchlists, signals (Analyst agent, issue #2), briefings
(Advisor agent, issue #3), and review states (reviewed/escalated/discarded +
justification, issue #4). See:
    docs/specs/2026-07-11-track5-product-focus.md
    GitHub issue #1 (StevSant/taws) — "feat: wire Supabase schema, auth, and
    watchlist persistence"

Compliance note (HU3): every table here is alert/task-shaped. There is no
buy/sell/order/quantity/price_target column anywhere in this schema, and there
must never be one — see the product's compliance stance in the spec above.

Revision ID: 0001
Revises:
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- gen_random_uuid() is built into Postgres 13+; this is a no-op guard on Supabase,
-- kept for portability.
create extension if not exists pgcrypto;

-- =============================================================================
-- watchlists — a named, user-owned collection of tracked instruments.
-- =============================================================================
create table if not exists public.watchlists (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,
    created_at timestamptz not null default now()
);

create index if not exists watchlists_user_id_idx on public.watchlists (user_id);

alter table public.watchlists enable row level security;

-- Owner-only: a user can only see/create/update/delete their own watchlists.
create policy "watchlists_select_own" on public.watchlists
    for select using (auth.uid() = user_id);

create policy "watchlists_insert_own" on public.watchlists
    for insert with check (auth.uid() = user_id);

create policy "watchlists_update_own" on public.watchlists
    for update using (auth.uid() = user_id);

create policy "watchlists_delete_own" on public.watchlists
    for delete using (auth.uid() = user_id);

-- =============================================================================
-- watchlist_items — instruments tracked inside a watchlist (by symbol; the
-- curated instrument universe is config-driven, not a database table, so there's
-- no FK to an `instruments` table).
-- =============================================================================
create table if not exists public.watchlist_items (
    id uuid primary key default gen_random_uuid(),
    watchlist_id uuid not null references public.watchlists (id) on delete cascade,
    symbol text not null,
    added_at timestamptz not null default now(),
    unique (watchlist_id, symbol)
);

create index if not exists watchlist_items_watchlist_id_idx
    on public.watchlist_items (watchlist_id);

alter table public.watchlist_items enable row level security;

-- Owner-only via the parent watchlist (watchlist_items has no user_id of its own).
create policy "watchlist_items_select_own" on public.watchlist_items
    for select using (
        exists (
            select 1 from public.watchlists w
            where w.id = watchlist_items.watchlist_id and w.user_id = auth.uid()
        )
    );

create policy "watchlist_items_insert_own" on public.watchlist_items
    for insert with check (
        exists (
            select 1 from public.watchlists w
            where w.id = watchlist_items.watchlist_id and w.user_id = auth.uid()
        )
    );

create policy "watchlist_items_delete_own" on public.watchlist_items
    for delete using (
        exists (
            select 1 from public.watchlists w
            where w.id = watchlist_items.watchlist_id and w.user_id = auth.uid()
        )
    );

-- =============================================================================
-- signals — Analyst-agent impact calls per instrument (issue #2 writes these).
--
-- Signals are NOT user-owned: they're market-wide analysis of an instrument, not
-- scoped to one user's data. RLS is still enabled (defense-in-depth in case a
-- client ever queries Supabase directly with a user JWT instead of only through
-- this backend), but the only policy is a read policy for any authenticated user.
-- The backend writes signals using the Supabase service-role key (see
-- SupabaseSignalRepository / SUPABASE_KEY in .env.example), which bypasses RLS
-- entirely, by design — regular users can read but never write rows directly.
-- =============================================================================
create table if not exists public.signals (
    id uuid primary key default gen_random_uuid(),
    instrument_symbol text not null,
    impact_class text not null
        check (impact_class in ('positive', 'negative', 'neutral', 'uncertain')),
    confidence numeric(5, 4) not null check (confidence >= 0 and confidence <= 1),
    evidence jsonb not null default '[]'::jsonb,
    price_delta numeric,
    disclaimer text not null,
    created_at timestamptz not null default now()
);

create index if not exists signals_instrument_symbol_idx on public.signals (instrument_symbol);

alter table public.signals enable row level security;

create policy "signals_select_authenticated" on public.signals
    for select using (auth.role() = 'authenticated');

-- =============================================================================
-- briefings — Advisor-agent summaries per watchlist (issue #3 writes these).
--
-- Like signals, briefings are written by an agent via the service-role key
-- (bypassing RLS). Read access is scoped to the owner of the linked watchlist,
-- since a briefing is meaningful only in the context of a user's own watchlist.
-- =============================================================================
create table if not exists public.briefings (
    id uuid primary key default gen_random_uuid(),
    watchlist_id uuid not null references public.watchlists (id) on delete cascade,
    summary text not null,
    linked_signal_ids uuid[] not null default '{}',
    disclaimer text not null,
    created_at timestamptz not null default now()
);

create index if not exists briefings_watchlist_id_idx on public.briefings (watchlist_id);

alter table public.briefings enable row level security;

create policy "briefings_select_own_watchlist" on public.briefings
    for select using (
        exists (
            select 1 from public.watchlists w
            where w.id = briefings.watchlist_id and w.user_id = auth.uid()
        )
    );

-- =============================================================================
-- review_states — reviewer decisions (reviewed/escalated/discarded) + required
-- justification, on a signal or a briefing. Append-only audit trail: issue #4's
-- review use case inserts new rows here, never updates/deletes existing ones, so
-- history is never lost. `entity_id` intentionally has no FK (it points at either
-- `signals.id` or `briefings.id` depending on `entity_type` — a single FK can't
-- express that; enforcing referential integrity across both is left to the
-- application layer, consistent with the persistence-only scope of this issue).
-- =============================================================================
create table if not exists public.review_states (
    id uuid primary key default gen_random_uuid(),
    entity_type text not null check (entity_type in ('signal', 'briefing')),
    entity_id uuid not null,
    user_id uuid not null references auth.users (id) on delete cascade,
    decision text not null check (decision in ('reviewed', 'escalated', 'discarded')),
    justification text not null check (char_length(justification) > 0),
    created_at timestamptz not null default now()
);

create index if not exists review_states_entity_idx
    on public.review_states (entity_type, entity_id);
create index if not exists review_states_user_id_idx on public.review_states (user_id);

alter table public.review_states enable row level security;

-- Per-user, per the issue: a user can see/create their own review decisions.
-- No update/delete policy anywhere (including for the owner) — the audit trail is
-- immutable by design; a changed mind is a new row, not a mutated one.
create policy "review_states_select_own" on public.review_states
    for select using (auth.uid() = user_id);

create policy "review_states_insert_own" on public.review_states
    for insert with check (auth.uid() = user_id);
"""

_DOWNGRADE_SQL = """
drop table if exists public.review_states cascade;
drop table if exists public.briefings cascade;
drop table if exists public.signals cascade;
drop table if exists public.watchlist_items cascade;
drop table if exists public.watchlists cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
