from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    """Port for a vector similarity store, backing RAG retrieval."""

    @abstractmethod
    async def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        """Insert or update vectors (and optional metadata) by id."""
        raise NotImplementedError

    @abstractmethod
    async def search(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """Return the `top_k` nearest matches to `query_vector`."""
        raise NotImplementedError
