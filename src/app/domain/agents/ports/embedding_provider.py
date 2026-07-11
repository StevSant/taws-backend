from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Port for turning text into vector embeddings, for RAG / semantic search."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        raise NotImplementedError
