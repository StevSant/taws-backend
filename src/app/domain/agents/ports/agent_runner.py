from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.domain.agents.entities import Message


class AgentRunner(ABC):
    """Port that wraps an agent graph (e.g. a compiled LangGraph graph).

    Supports multiple agents/tools, async execution, and streaming without the
    application layer knowing anything about LangGraph or any specific graph shape.
    """

    @abstractmethod
    async def stream(self, thread_id: str, message: Message) -> AsyncIterator[str]:
        """Run the agent for `thread_id` on `message`, yielding tokens as they arrive."""
        raise NotImplementedError
        yield ""  # pragma: no cover — unreachable; keeps this an async generator for typing
