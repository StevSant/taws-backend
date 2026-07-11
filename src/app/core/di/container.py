from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.core.config import Settings, get_settings
from app.domain.agents.ports import (
    AgentMemory,
    AgentRunner,
    EmbeddingProvider,
    LLMProvider,
    VectorStore,
)
from app.domain.chat.ports import ConversationRepository
from app.infrastructure.agents import LangGraphAgentRunner, build_chat_graph
from app.infrastructure.embeddings import OpenAIEmbeddings
from app.infrastructure.llm import OpenAIProvider, build_chat_model
from app.infrastructure.memory import InMemoryCheckpointer, RedisCheckpointer
from app.infrastructure.persistence import SupabaseConversationRepository
from app.infrastructure.vectorstore import PgvectorStore


class Container:
    """Wires domain ports to infrastructure adapters, based on `Settings`.

    This is the single place that decides which adapter implements which port. To
    swap a provider (e.g. add Anthropic): create the adapter in `infrastructure/`,
    then change the relevant `get_*` method below — nothing else in the codebase
    needs to know.

    Every adapter is built lazily and cached on first access, so each is a
    process-wide singleton for the lifetime of this `Container` (itself cached by
    `get_container`) — e.g. the `AsyncOpenAI` client, the LangChain chat model, the
    compiled graph, and the `AgentRunner` are each constructed once.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llm_provider: LLMProvider | None = None
        self._embedding_provider: EmbeddingProvider | None = None
        self._vector_store: VectorStore | None = None
        self._agent_memory: AgentMemory | None = None
        self._conversation_repository: ConversationRepository | None = None
        self._chat_model: BaseChatModel | None = None
        self._chat_graph: Any | None = None
        self._agent_runner: AgentRunner | None = None

    def get_llm_provider(self) -> LLMProvider:
        if self._llm_provider is None:
            self._llm_provider = OpenAIProvider(
                api_key=self._settings.openai_api_key, model=self._settings.openai_model
            )
        return self._llm_provider

    def get_embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            self._embedding_provider = OpenAIEmbeddings(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_embedding_model,
            )
        return self._embedding_provider

    def get_vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = PgvectorStore(database_url=self._settings.database_url)
        return self._vector_store

    def get_agent_memory(self) -> AgentMemory:
        if self._agent_memory is None:
            # Key fallback logic: Redis (Upstash) when configured, in-memory otherwise —
            # so local/offline dev and CI never break for lack of a Redis URL.
            if self._settings.redis_url:
                self._agent_memory = RedisCheckpointer(redis_url=self._settings.redis_url)
            else:
                self._agent_memory = InMemoryCheckpointer()
        return self._agent_memory

    def get_conversation_repository(self) -> ConversationRepository:
        if self._conversation_repository is None:
            self._conversation_repository = SupabaseConversationRepository(
                supabase_url=self._settings.supabase_url,
                supabase_key=self._settings.supabase_key,
            )
        return self._conversation_repository

    def get_agent_runner(self) -> AgentRunner:
        """Return the cached `AgentRunner`, built from the chat model + checkpointer.

        See `infrastructure/llm/chat_model_factory.build_chat_model` to swap the LLM
        provider behind agent graphs, and `infrastructure/agents/chat_graph.
        build_chat_graph` to change the graph shape — this method only wires them
        together.
        """
        if self._agent_runner is None:
            self._agent_runner = LangGraphAgentRunner(graph=self._get_chat_graph())
        return self._agent_runner

    def _get_chat_model(self) -> BaseChatModel:
        if self._chat_model is None:
            self._chat_model = build_chat_model(self._settings)
        return self._chat_model

    def _get_chat_graph(self) -> Any:
        if self._chat_graph is None:
            checkpointer = self.get_agent_memory().get_checkpointer()
            self._chat_graph = build_chat_graph(self._get_chat_model(), checkpointer)
        return self._chat_graph


@lru_cache
def get_container() -> Container:
    """Return a process-wide cached Container, built from the cached Settings."""
    return Container(settings=get_settings())
