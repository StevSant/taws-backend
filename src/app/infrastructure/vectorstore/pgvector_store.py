from typing import Any

from app.domain.agents.ports import VectorStore


class PgvectorStore(VectorStore):
    """VectorStore adapter backed by Postgres + pgvector (Supabase).

    Stub for the hackathon skeleton: RAG is a later-phase concern (see architecture
    spec, Phase 3). Wire an async Postgres connection (asyncpg / SQLAlchemy async)
    here before use.
    """

    def __init__(self, database_url: str | None) -> None:
        self._database_url = database_url

    async def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        raise NotImplementedError("PgvectorStore.upsert is a stub — wire a Postgres connection.")

    async def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        raise NotImplementedError("PgvectorStore.search is a stub — wire a Postgres connection.")
