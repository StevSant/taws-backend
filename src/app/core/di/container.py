from functools import lru_cache

from app.core.config import Settings, get_settings
from app.domain.agents.ports import AgentMemory, EmbeddingProvider, LLMProvider, VectorStore
from app.domain.chat.ports import ConversationRepository
from app.infrastructure.embeddings import OpenAIEmbeddings
from app.infrastructure.llm import OpenAIProvider
from app.infrastructure.memory import InMemoryCheckpointer, RedisCheckpointer
from app.infrastructure.persistence import SupabaseConversationRepository
from app.infrastructure.vectorstore import PgvectorStore


class Container:
    """Wires domain ports to infrastructure adapters, based on `Settings`.

    This is the single place that decides which adapter implements which port. To
    swap a provider (e.g. add Anthropic): create the adapter in `infrastructure/`,
    then change the relevant `get_*` method below — nothing else in the codebase
    needs to know.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_llm_provider(self) -> LLMProvider:
        return OpenAIProvider(
            api_key=self._settings.openai_api_key, model=self._settings.openai_model
        )

    def get_embedding_provider(self) -> EmbeddingProvider:
        return OpenAIEmbeddings(
            api_key=self._settings.openai_api_key,
            model=self._settings.openai_embedding_model,
        )

    def get_vector_store(self) -> VectorStore:
        return PgvectorStore(database_url=self._settings.database_url)

    def get_agent_memory(self) -> AgentMemory:
        # Key fallback logic: Redis (Upstash) when configured, in-memory otherwise —
        # so local/offline dev and CI never break for lack of a Redis URL.
        if self._settings.redis_url:
            return RedisCheckpointer(redis_url=self._settings.redis_url)
        return InMemoryCheckpointer()

    def get_conversation_repository(self) -> ConversationRepository:
        return SupabaseConversationRepository(
            supabase_url=self._settings.supabase_url,
            supabase_key=self._settings.supabase_key,
        )


@lru_cache
def get_container() -> Container:
    """Return a process-wide cached Container, built from the cached Settings."""
    return Container(settings=get_settings())
