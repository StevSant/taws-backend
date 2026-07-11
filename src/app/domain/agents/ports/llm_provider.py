from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.domain.agents.entities import Message


class LLMProvider(ABC):
    """Port for a chat-completion capable LLM backend.

    Adapters: OpenAI (primary), Anthropic, Gemini, Ollama, ... Swapping the backend
    only means adding a new adapter in `infrastructure/llm/` and binding it in the
    DI container — this port never changes.
    """

    @abstractmethod
    async def complete(self, messages: list[Message]) -> str:
        """Return a single, fully-formed response for the given conversation."""
        raise NotImplementedError

    @abstractmethod
    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """Yield response tokens as they become available."""
        raise NotImplementedError
        yield ""  # pragma: no cover — unreachable; keeps this an async generator for typing
