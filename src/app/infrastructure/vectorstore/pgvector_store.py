from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.domain.agents.ports import VectorStore

_TABLE = "public.historical_analogs"
_NO_DATABASE_URL_ERROR = "[PgvectorStore] DATABASE_URL is not configured."


class PgvectorStore(VectorStore):
    """VectorStore adapter backed by Postgres + pgvector (Supabase).

    Talks to Postgres directly via `psycopg` (v3 — already a dependency, used by Alembic) rather
    than through `supabase-py`/PostgREST, since pgvector's `<=>` distance operator and the
    `vector` column type aren't exposed over PostgREST. `database_url` must be the direct
    Postgres connection string (the same one Alembic/`migrations/env.py` uses), not the
    `SUPABASE_URL`/`SUPABASE_KEY` REST credentials.

    A new connection is opened per call — acceptable at hackathon scale (no pooling); revisit
    with a connection pool (e.g. `psycopg_pool`) if this becomes a hot path.

    Vectors are passed as `%s::vector` text literals (`[0.1,0.2,...]`) rather than via the
    `pgvector` Python package's psycopg type adapter, to avoid adding a new dependency for a
    single cast — see `_to_vector_literal`.

    Backing table: `public.historical_analogs` (migration `0003`), storing the historical-analogs
    RAG data for issue #15 — see `application/analogs/use_cases/` for the read/write use cases
    that call this adapter through the `VectorStore` port.
    """

    def __init__(self, database_url: str | None) -> None:
        self._database_url = database_url

    async def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        if not self._database_url:
            raise RuntimeError(_NO_DATABASE_URL_ERROR)

        rows_metadata = metadata or [{} for _ in ids]
        async with (
            await psycopg.AsyncConnection.connect(self._database_url) as conn,
            conn.cursor() as cur,
        ):
            for row_id, vector, meta in zip(ids, vectors, rows_metadata, strict=True):
                await cur.execute(
                    f"""
                    insert into {_TABLE} (id, instrument_symbol, embedding, metadata)
                    values (%s, %s, %s::vector, %s)
                    on conflict (id) do update set
                        instrument_symbol = excluded.instrument_symbol,
                        embedding = excluded.embedding,
                        metadata = excluded.metadata
                    """,
                    (
                        row_id,
                        meta.get("instrument_symbol", ""),
                        _to_vector_literal(vector),
                        Jsonb(meta),
                    ),
                )
            await conn.commit()

    async def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        if not self._database_url:
            raise RuntimeError(_NO_DATABASE_URL_ERROR)

        vector_literal = _to_vector_literal(query_vector)
        async with (
            await psycopg.AsyncConnection.connect(self._database_url) as conn,
            conn.cursor() as cur,
        ):
            await cur.execute(
                f"""
                select id, instrument_symbol, metadata, embedding <=> %s::vector as distance
                from {_TABLE}
                order by embedding <=> %s::vector
                limit %s
                """,
                (vector_literal, vector_literal, top_k),
            )
            rows = await cur.fetchall()

        return [
            {
                "id": row[0],
                "instrument_symbol": row[1],
                "metadata": row[2],
                "distance": float(row[3]),
            }
            for row in rows
        ]


def _to_vector_literal(vector: list[float]) -> str:
    """Format a Python vector as a pgvector text literal, e.g. `[0.1,0.2,0.3]`."""
    return "[" + ",".join(repr(float(component)) for component in vector) + "]"
