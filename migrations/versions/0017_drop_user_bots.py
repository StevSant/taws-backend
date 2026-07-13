"""drop user_bots (BotFather per-user bot registration removed)

The product no longer asks each user to create their own bot via BotFather and register
its token. Telegram is now ONE shared bot: the user requests a deep-link token
(`POST /api/v1/telegram/link-token`), opens `https://t.me/<bot>?start=<token>`, and the
shared webhook (`POST /api/v1/telegram/webhook`) resolves it through `LinkTelegramAccount`
into a row in `telegram_links`. Every command handler and the notification channel resolve
their recipient through `telegram_links` — `user_bots` has no reader left.

Dropping it also retires the one place this schema stored a third-party API credential
(`user_bots.bot_token`, plain text): the shared bot's token now lives only in the backend's
`TELEGRAM_BOT_TOKEN` env var, never in the database.

Compliance note (same stance as every other migration in this schema): this revision only
drops a table. There is no buy/sell/order/quantity/price_target column anywhere in this
schema, and there must never be one.

`downgrade()` recreates the table exactly as migration 0009b defined it — full DDL, RLS
enabled, and all four `auth.uid()`-scoped policies. It cannot restore the ROWS, which the
drop destroys; that is accepted, since the registrations it held are no longer reachable
by any code path.

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
drop table if exists public.user_bots cascade;
"""

_DOWNGRADE_SQL = """
-- =============================================================================
-- user_bots — one registered Telegram bot per user (restored from migration 0009b).
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


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
