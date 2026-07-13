"""conversations + conversation_messages

Durable chat history. Until now chat was the ONLY feature with no table behind it:
`SupabaseConversationRepository` was a stub holding an in-process dict, the one use case
that called its `save()` was never routed, and the frontend kept sessions in
`localStorage` alone. Per-thread history therefore lived exclusively in the LangGraph
checkpointer — a cache, not a store — which silently degrades to `InMemoryCheckpointer`
when `REDIS_URL` is unset, so a restart or a second worker lost every conversation.

Two tables:

- `conversations` — one row per chat thread, owned by a user. Its `id` IS the
  `thread_id` the frontend generates and sends to `POST /api/v1/chat/stream`, so the
  agent checkpointer and this table are keyed identically and can never drift apart.
- `conversation_messages` — the ordered turns of a conversation, owner-scoped through
  the parent row (the same "child table has no user_id of its own" RLS shape as
  `watchlist_items` in 0001).

`conversations.id` is `text`, NOT `uuid`, on purpose. The client mints the id, and two of
its paths are not UUIDs: `ChatSessionsStore` falls back to `${Date.now()}-${Math.random()}`
where `crypto.randomUUID` is unavailable (non-HTTPS origins), and the router substitutes
the literal `"default"` when a request omits `thread_id`. A `uuid` column would reject
both with a 22P02 at insert time, turning a degraded-but-working chat into a broken one.

`ordinal` (not `position`) orders the turns: `position` is a Postgres `col_name_keyword`
and needs quoting to be used as a column name. The `(conversation_id, ordinal)` unique
constraint makes an append idempotent under a retry — a duplicated write conflicts
instead of silently doubling a turn.

Compliance note (HU3, same stance as every other migration in this schema): these are
plain conversational records. There is no buy/sell/order/quantity/price_target column
here, and there must never be one.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-13

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
-- =============================================================================
-- conversations — one chat thread per row. `id` is the client-minted thread_id
-- (text, not uuid — see the module docstring), so this table and the LangGraph
-- checkpointer are keyed by the same value.
-- =============================================================================
create table if not exists public.conversations (
    id text primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    title text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- The sidebar lists a user's threads most-recently-updated first; this index serves
-- that query directly.
create index if not exists conversations_user_id_updated_at_idx
    on public.conversations (user_id, updated_at desc);

alter table public.conversations enable row level security;

-- Owner-only: a user can only see/create/update/delete their own conversations.
create policy "conversations_select_own" on public.conversations
    for select using (auth.uid() = user_id);

create policy "conversations_insert_own" on public.conversations
    for insert with check (auth.uid() = user_id);

create policy "conversations_update_own" on public.conversations
    for update using (auth.uid() = user_id);

create policy "conversations_delete_own" on public.conversations
    for delete using (auth.uid() = user_id);

-- =============================================================================
-- conversation_messages — the ordered turns of one conversation. Cascades with
-- its parent, so deleting a thread takes its messages with it.
-- =============================================================================
create table if not exists public.conversation_messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id text not null
        references public.conversations (id) on delete cascade,
    role text not null check (role in ('system', 'user', 'assistant')),
    content text not null,
    ordinal integer not null,
    created_at timestamptz not null default now(),
    unique (conversation_id, ordinal)
);

create index if not exists conversation_messages_conversation_id_ordinal_idx
    on public.conversation_messages (conversation_id, ordinal);

alter table public.conversation_messages enable row level security;

-- Owner-only via the parent conversation (conversation_messages has no user_id of
-- its own) — same shape as watchlist_items' policies in 0001.
create policy "conversation_messages_select_own" on public.conversation_messages
    for select using (
        exists (
            select 1 from public.conversations c
            where c.id = conversation_messages.conversation_id and c.user_id = auth.uid()
        )
    );

create policy "conversation_messages_insert_own" on public.conversation_messages
    for insert with check (
        exists (
            select 1 from public.conversations c
            where c.id = conversation_messages.conversation_id and c.user_id = auth.uid()
        )
    );

create policy "conversation_messages_delete_own" on public.conversation_messages
    for delete using (
        exists (
            select 1 from public.conversations c
            where c.id = conversation_messages.conversation_id and c.user_id = auth.uid()
        )
    );
"""

_DOWNGRADE_SQL = """
-- conversation_messages cascades from conversations, but drop it explicitly first so
-- the downgrade doesn't depend on cascade ordering.
drop table if exists public.conversation_messages cascade;
drop table if exists public.conversations cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
