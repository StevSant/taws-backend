"""user_notes

Per-user free-text notes (issue #62), surfaced by the shared Guía/Notas panel on both the
Briefings and Scenario Lab pages. Owner-only, mirrors the RLS pattern established by
`watchlists` in 0001.

Compliance note (HU3): like every other table in this schema, `user_notes` is a plain
free-text/task-shaped record. There is no buy/sell/order/quantity/price_target column, and
there must never be one — see the product's compliance stance.

Revision ID: 0011b
Revises: 0011
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011b"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- user_notes — per-user free-text notes (issue #62). Not tied to a briefing or
-- scenario: the same notes follow the user across both pages.
-- =============================================================================
create table if not exists public.user_notes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    body text not null check (char_length(body) > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists user_notes_user_id_idx on public.user_notes (user_id);

alter table public.user_notes enable row level security;

-- Owner-only: a user can only see/create/update/delete their own notes.
create policy "user_notes_select_own" on public.user_notes
    for select using (auth.uid() = user_id);

create policy "user_notes_insert_own" on public.user_notes
    for insert with check (auth.uid() = user_id);

create policy "user_notes_update_own" on public.user_notes
    for update using (auth.uid() = user_id);

create policy "user_notes_delete_own" on public.user_notes
    for delete using (auth.uid() = user_id);
"""

_DOWNGRADE_SQL = """
drop table if exists public.user_notes cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
