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
the embedding model changes to one with a different output width, this column needs a
follow-up migration.

No approximate-nearest-neighbor index on `embedding` yet — see the comment in the SQL
below for why (T1 row counts don't support tuning `ivfflat`'s `lists` parameter
correctly, and an under-tuned one silently returns wrong results, not just slower ones).

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

-- No ANN index on `embedding` yet — deliberate, not an oversight. `ivfflat`'s `lists`
-- parameter must be sized from real row-count data (pgvector's own guidance: roughly
-- `lists ≈ rows / 1000`, minimum ~10) to build well-populated, well-separated lists; at
-- T1 scale (hundreds to low-thousands of rows) any `lists` value chosen without that
-- data either degenerates to near-empty lists or is moot next to a sequential scan,
-- and `ivfflat.probes` defaults to 1, so an under-tuned index doesn't just cost a bit
-- of speed — it can silently return the WRONG nearest neighbors (confirmed by a live
-- repro against a real pgvector container: with `lists = 100` on 32 rows, cosine search
-- missed the true second-nearest match entirely and returned worse ones instead). A
-- sequential scan is fast and, more importantly, CORRECT at this scale — add an index
-- (ivfflat retuned from real row counts, or `hnsw`, which doesn't need row-count-based
-- tuning) as follow-up work once the table's real production size is known.
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
