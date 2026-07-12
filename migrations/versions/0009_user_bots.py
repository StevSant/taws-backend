"""user_bots (per-user Telegram bot registration)

Track-5 T2 data layer: `user_bots` — per-user Telegram bot registration (issue #19
extension). Each user can register their own Telegram bot (created via BotFather) to
receive notifications and handle chat messages through their own bot.

One row per `user_id` (unique constraint below), same visibility model as `watchlists`
(migration 0001). Same "backend writes with the service-role key (bypasses RLS); RLS
policies here are defense-in-depth scoped to `auth.uid()`" pattern as every other
user-owned table in this schema.

`bot_token` is stored as plain text (not encrypted) — the Supabase project's Postgres
connection is already TLS-encrypted, and the token is scoped to the user's own bot.
If encryption-at-rest is needed later, a `pgcrypto` `pgp_sym_encrypt` column can be
added in a follow-up migration.

Compliance note (same stance as every other migration in this schema): every column here
is bot-registration-shaped. There is no buy/sell/order/quantity/price_target column
anywhere in this schema, and there must never be one.

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
-- user_bots — one registered Telegram bot per user.
-- Unique on user_id: a user can register at most one bot.
-- =============================================================================
create table if not exists public.user_bots (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    bot_token text not null,
    bot_username text not null,
    chat_id text not null,
    created_at timestamptz not null default now(),
    unique (user_id)
);

alter table public.user_bots enable row level security;

create policy "user_bots_select_own" on public.user_bots
    for select using (auth.uid() = user_id);

create policy "user_bots_insert_own" on public.user_bots
    for insert with check (auth.uid() = user_id);

create policy "user_bots_update_own" on public.user_bots
    for update using (auth.uid() = user_id);

create policy "user_bots_delete_own" on public.user_bots
    for delete using (auth.uid() = user_id);
"""

_DOWNGRADE_SQL = """
drop table if exists public.user_bots cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
