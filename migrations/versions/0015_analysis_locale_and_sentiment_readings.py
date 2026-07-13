"""analysis locale cache key + sentiment_readings (shared-analysis caching)

Issue #29 / `docs/specs/2026-07-12-shared-asset-analysis-caching-design.md`. Shared asset
analysis was generated append-only with no freshness cache: every generate call re-ran the
full LLM pipeline and inserted another row for the same instrument. This revision lays the
data layer for caching it.

Three changes, all serving the same cache key:

1. `locale` on `signals` and `scenarios`. The analytical fields these tables hold
   (`thesis`/`key_drivers`/`risk_factors`, `narrative`/`recommended_actions`) are LOCALIZED,
   but neither table recorded which language they were written in. A symbol-only cache would
   therefore happily serve a Spanish thesis to an English request. The cache key is
   `(instrument_symbol, locale)` — and `(preset_id, locale)` for scenarios — so `locale` has
   to be a real column, not a JSONB field. Existing rows are backfilled to 'en': every row
   written before this migration came from a pipeline whose only default locale was 'en'
   (`Settings.default_locale`).

2. Composite indexes `(instrument_symbol, locale, created_at desc)` /
   `(preset_id, locale, created_at desc)`. Both new access patterns — `get_latest_*` (a single
   `order by created_at desc limit 1`) and `prune_*` (the same ordering, sliced) — are covered
   by one index each. The pre-existing `signals_instrument_symbol_idx` can't serve them: it
   has no locale and no ordering, so the latest-lookup degrades to a full per-symbol scan plus
   an in-memory sort. It is kept, since `list_for_instrument` (the review/audit-trail read,
   which is deliberately locale-agnostic) still uses it.

3. `sentiment_readings` — a NEW table. Sentiment was the worst case of all: `AnalyzeSentiment`
   recomputed a tone score on every call and never wrote it down, so the cost was pure waste
   with nothing to reuse. Caching it requires persisting it first. `locale` is present from the
   start, so this table never needs the backfill above.

Ownership: `sentiment_readings` follows `signals`/`news_items` exactly — NOT user-owned. A tone
score is market analysis about an instrument, not private data about whoever asked for it, so
there is no `user_id`. RLS is enabled as defense-in-depth (in case a client ever queries
Supabase directly with a user JWT rather than only through this backend), with a single
read-policy for any authenticated user; the backend writes with the service-role key, which
bypasses RLS.

`tone_label` is a plain `text` column constrained by a `check`, not a Postgres enum — the same
"app-layer enum, DB-layer check constraint" call `review_states.state` (0002),
`scenario_monitors.status` (0008), and `news_items.analysis_status` (0009) make. Its values must
stay in sync with `SentimentLabel` (`src/app/domain/sentiment/entities/sentiment_label.py`).

Compliance note (HU3): as everywhere else in this schema, there is no buy/sell/order/quantity/
price_target column here, and there must never be one.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- 1. locale as part of the analysis cache key (signals, scenarios).
--    `default 'en'` backfills every pre-existing row in the same statement.
-- =============================================================================
alter table public.signals
    add column if not exists locale text not null default 'en';

comment on column public.signals.locale is
    'Language the LLM-authored fields (thesis/key_drivers/risk_factors) were written in. '
    'Part of the freshness cache key (instrument_symbol, locale) — issue #29.';

alter table public.scenarios
    add column if not exists locale text not null default 'en';

comment on column public.scenarios.locale is
    'Language title/narrative/recommended_actions were written in. Part of the freshness '
    'cache key (preset_id, locale) for preset runs — issue #29. Free-form runs are not cached.';

-- =============================================================================
-- 2. Composite indexes covering get_latest_* and prune_* in a single scan.
-- =============================================================================
create index if not exists signals_symbol_locale_created_idx
    on public.signals (instrument_symbol, locale, created_at desc);

create index if not exists scenarios_preset_locale_created_idx
    on public.scenarios (preset_id, locale, created_at desc);

-- =============================================================================
-- 3. sentiment_readings — Sentiment Analyst output, persisted for the first time.
--    Shared (no user_id), same visibility model as `signals` (migration 0001).
-- =============================================================================
create table if not exists public.sentiment_readings (
    id uuid primary key default gen_random_uuid(),
    instrument_symbol text not null,
    locale text not null,
    tone_score numeric(5, 4) not null check (tone_score >= -1 and tone_score <= 1),
    tone_label text not null
        check (tone_label in ('bearish', 'neutral', 'bullish')),
    fear_greed jsonb not null default '{}'::jsonb,
    evidence jsonb not null default '[]'::jsonb,
    rationale text not null,
    disclaimer text not null,
    created_at timestamptz not null default now()
);

comment on table public.sentiment_readings is
    'Sentiment Analyst tone readings per (instrument_symbol, locale). Shared/global market '
    'analysis, NOT user-owned — same ownership model as signals. Issue #29.';

comment on column public.sentiment_readings.fear_greed is
    'The market-wide Fear & Greed reading attached to this tone score, stored alongside it so '
    'a cached reading rehydrates completely instead of gluing an old tone score to a fresh '
    'index value.';

create index if not exists sentiment_readings_symbol_locale_created_idx
    on public.sentiment_readings (instrument_symbol, locale, created_at desc);

alter table public.sentiment_readings enable row level security;

create policy "sentiment_readings_select_authenticated" on public.sentiment_readings
    for select using (auth.role() = 'authenticated');
"""

_DOWNGRADE_SQL = """
drop table if exists public.sentiment_readings cascade;

drop index if exists public.scenarios_preset_locale_created_idx;
drop index if exists public.signals_symbol_locale_created_idx;

alter table public.scenarios drop column if exists locale;
alter table public.signals drop column if exists locale;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
