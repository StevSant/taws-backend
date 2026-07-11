"""scenarios (Scenario Simulation graph results)

Track-5 T1 data layer: `scenarios` — the Scenario Simulation graph's persisted
`ScenarioResult`s (issue #12 — "feat: build Scenario Simulation engine"). Backs the
`ScenarioRepository` port's `SupabaseScenarioRepository` adapter
(`src/app/infrastructure/persistence/supabase_scenario_repository.py`), written to by the
graph's Compliance step right after `ReviewCompliance` passes, and read back by
`GET /api/v1/scenarios/{id}` / `GET /api/v1/scenarios`.

Ownership note: like `signals` (not like `watchlists`/`briefings`), `scenarios` are NOT
user-owned — a preset run ("Fed +50bp") has no single owner, and even a free-form run is
research about the market, not private data about the user who typed it. Same RLS shape
as `signals` (migration 0001): the backend writes via the service-role key (bypassing
RLS); any authenticated user can read.

`spec`/`impact_map`/`consequence_chain` are stored as JSONB — nested structured shapes,
same choice migration 0001 makes for `signals.evidence`. `preset_id` is denormalized out
of `spec` into its own indexed column for filtering; the JSONB `spec` blob stays the
source of truth.

Compliance note (same stance as migration 0001): every column here is alert/research-
shaped. There is no buy/sell/order/quantity/price_target column anywhere in this schema,
and there must never be one.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- scenarios — Scenario Simulation graph results (issue #12). Not user-owned — see the
-- module docstring above for the same-visibility-as-`signals` rationale.
-- =============================================================================
create table if not exists public.scenarios (
    id uuid primary key default gen_random_uuid(),
    preset_id text,
    title text not null,
    narrative text not null,
    spec jsonb not null,
    impact_map jsonb not null default '[]'::jsonb,
    consequence_chain jsonb not null,
    recommended_actions text[] not null default '{}',
    disclaimer text not null,
    created_at timestamptz not null default now()
);

create index if not exists scenarios_preset_id_idx on public.scenarios (preset_id);
create index if not exists scenarios_created_at_idx on public.scenarios (created_at desc);

alter table public.scenarios enable row level security;

create policy "scenarios_select_authenticated" on public.scenarios
    for select using (auth.role() = 'authenticated');
"""

_DOWNGRADE_SQL = """
drop table if exists public.scenarios cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
