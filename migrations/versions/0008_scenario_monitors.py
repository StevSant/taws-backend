"""scenario_monitors (armed Scenario Monitors)

Track-5 T2 data layer: `scenario_monitors` — armed Watchdog rules on top of a saved
`ScenarioResult` (issue #18 — "arm Scenario Monitors via Watchdog integration"). Backs the
`ScenarioRepository` port's monitor methods (`arm_monitor`/`get_monitor_for_user`/
`list_armed_monitors`/`mark_monitor_matched`/`mark_monitor_expired`/`disarm_monitor`) on
`src/app/infrastructure/persistence/supabase_scenario_repository.py`.

Ownership note: UNLIKE `scenarios` (migration 0006, not user-owned), `scenario_monitors`
IS user-owned — one row per `(scenario_id, user_id)` (see the unique constraint below),
same visibility model as `watchlists` (migration 0001). Same "backend writes with the
service-role key (bypasses RLS); RLS policies here are defense-in-depth scoped to
`auth.uid()`" pattern as every other user-owned table in this schema.

`status` is a plain `text` column (not a Postgres enum) constrained to the three
`ScenarioMonitorStatus` values — same "app-layer enum, DB-layer check constraint" choice
`review_states.state` makes in migration 0002, so adding a fourth status later is a
one-line `check` change, not an `ALTER TYPE`.

Compliance note (same stance as every other migration in this schema): every column here
is monitor/alert-shaped. There is no buy/sell/order/quantity/price_target column anywhere
in this schema, and there must never be one.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- scenario_monitors — one armed Watchdog rule per (scenario_id, user_id) (issue #18).
-- Unique on both columns together: re-arming the same scenario as the same user reuses
-- the existing row (see ArmScenarioMonitor) rather than creating a duplicate.
-- =============================================================================
create table if not exists public.scenario_monitors (
    id uuid primary key default gen_random_uuid(),
    scenario_id uuid not null references public.scenarios (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    status text not null default 'armed'
        check (status in ('armed', 'matched', 'expired')),
    armed_at timestamptz not null default now(),
    expires_at timestamptz not null,
    matched_at timestamptz,
    match_reason text,
    created_at timestamptz not null default now(),
    unique (scenario_id, user_id)
);

create index if not exists scenario_monitors_status_idx on public.scenario_monitors (status);
create index if not exists scenario_monitors_user_id_idx on public.scenario_monitors (user_id);

alter table public.scenario_monitors enable row level security;

create policy "scenario_monitors_select_own" on public.scenario_monitors
    for select using (auth.uid() = user_id);

create policy "scenario_monitors_insert_own" on public.scenario_monitors
    for insert with check (auth.uid() = user_id);

create policy "scenario_monitors_update_own" on public.scenario_monitors
    for update using (auth.uid() = user_id);

create policy "scenario_monitors_delete_own" on public.scenario_monitors
    for delete using (auth.uid() = user_id);
"""

_DOWNGRADE_SQL = """
drop table if exists public.scenario_monitors cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
