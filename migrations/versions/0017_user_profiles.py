"""profiles — per-user preferences (preferred_locale)

Persists the language a logged-in user picked in the UI (issue #67), so the agent and every
AI-generated narrative answer in that language on any device — not just on the browser that
holds the `taws.locale` localStorage key. Owner-only, mirroring the RLS pattern established
by `watchlists` in 0001 and `user_notes` in 0011b.

`preferred_locale` is nullable: a row may exist with no preference yet (the caller then falls
back to `Settings.default_locale`, `es`). Keyed by `user_id` rather than a synthetic `id`
because a user has exactly one profile — that makes the upsert on
`PATCH /api/v1/profile` a plain conflict-on-primary-key.

Compliance note (HU3): like every other table in this schema, `profiles` holds preference
data only. There is no buy/sell/order/quantity/price_target column, and there must never be
one — see the product's compliance stance.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- profiles — per-user preferences (issue #67). One row per auth user.
-- =============================================================================
create table if not exists public.profiles (
    user_id uuid primary key references auth.users (id) on delete cascade,
    preferred_locale text
        check (preferred_locale is null or char_length(preferred_locale) between 2 and 35),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Owner-only: a user can only see/create/update their own profile. No delete policy —
-- a profile row dies with its `auth.users` row (on delete cascade), and nothing in the
-- app deletes one on its own.
create policy "profiles_select_own" on public.profiles
    for select using (auth.uid() = user_id);

create policy "profiles_insert_own" on public.profiles
    for insert with check (auth.uid() = user_id);

create policy "profiles_update_own" on public.profiles
    for update using (auth.uid() = user_id);
"""

_DOWNGRADE_SQL = """
drop table if exists public.profiles cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
