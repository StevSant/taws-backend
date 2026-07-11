"""historical_analogs (pgvector RAG store)

Track-5 T1 data layer: pgvector-backed historical analogs (issue #15 — "Historical analogs
(RAG) in signals and scenarios"). Backs the `VectorStore` port's `PgvectorStore` adapter
(`src/app/infrastructure/vectorstore/pgvector_store.py`), written to by
`application/analogs/use_cases/index_signal_analog.py` right after each `Signal` is persisted,
and read by `application/analogs/use_cases/find_historical_analogs.py` to surface
`[análogo histórico]`-tagged evidence on new signals (and, later, the Scenario engine's
context-gathering step — issue #12).

Vector width (1536) matches the default `OPENAI_EMBEDDING_MODEL`
(`text-embedding-3-small`, see `Settings.openai_embedding_model`) — like `signals.confidence`'s
`numeric(5, 4)` in migration 0001, this is a schema-level constant, not an app config value; if
the embedding model changes to one with a different output width, this column (and the index)
needs a follow-up migration.

Compliance note (HU3, same stance as migration 0001): `metadata` stores research-only fields
(instrument, impact class, a news summary, `price_delta` as a "realized outcome" proxy) — no
buy/sell/order/quantity/price_target field, and there must never be one.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_SQL = """
create extension if not exists vector;

-- =============================================================================
-- historical_analogs — embedded past signal events, retrieved via cosine distance as
-- "historical analog" evidence for new signals (issue #15). Written by the Analyst
-- pipeline via the service-role key (bypasses RLS), same visibility model as `signals`:
-- not user-owned, read-only for any authenticated user.
--
-- `id` is `text` (not `uuid`) so it can reuse the originating `signals.id` UUID string
-- directly as the analog's id, without a cross-type cast at the `VectorStore` port
-- boundary (`VectorStore.upsert(ids: list[str], ...)`).
-- =============================================================================
create table if not exists public.historical_analogs (
    id text primary key,
    instrument_symbol text not null,
    embedding vector(1536) not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists historical_analogs_instrument_symbol_idx
    on public.historical_analogs (instrument_symbol);

-- Approximate nearest-neighbor index for cosine distance (`<=>`), matching the operator
-- used by `PgvectorStore.search`. `lists = 100` is a reasonable default for a small
-- hackathon-scale table; revisit per pgvector's tuning guidance if row counts grow large.
create index if not exists historical_analogs_embedding_idx
    on public.historical_analogs using ivfflat (embedding vector_cosine_ops) with (lists = 100);

alter table public.historical_analogs enable row level security;

create policy "historical_analogs_select_authenticated" on public.historical_analogs
    for select using (auth.role() = 'authenticated');
"""

_DOWNGRADE_SQL = """
drop table if exists public.historical_analogs cascade;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
