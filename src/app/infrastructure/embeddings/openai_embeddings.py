from openai import AsyncOpenAI

from app.domain.agents.ports import EmbeddingProvider


class OpenAIEmbeddings(EmbeddingProvider):
    """EmbeddingProvider adapter backed by the OpenAI Embeddings API.

    Guarded like `OpenAIProvider`: without an API key, returns zero-vectors instead
    of crashing, so callers can be exercised before a key is configured.
    """

    def __init__(self, api_key: str | None, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client is None:
            return [[0.0] for _ in texts]

        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]
