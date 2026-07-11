from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.domain.agents.entities import AgentStreamEvent, Message, TokenEvent


class AgentRunner(ABC):
    """Port that wraps an agent graph (e.g. a compiled LangGraph graph).

    Supports multiple agents/tools, async execution, and streaming without the
    application layer knowing anything about LangGraph or any specific graph shape.
    """

    @abstractmethod
    async def stream(
        self, thread_id: str, message: Message, user_id: str
    ) -> AsyncIterator[AgentStreamEvent]:
        """Run the agent for `thread_id` on `message`, yielding stream events as they arrive.

        `user_id` identifies the authenticated caller and is threaded through to the
        underlying graph's config (e.g. for future per-tenant tool access) — it is not
        yet consumed by any node or tool.

        Yields `TokenEvent`s for assistant tokens and `TraceEvent`s for agent-routing/
        lifecycle hops (see `AgentStreamEvent`). Implementations must never let an
        exception escape this generator — catch it and yield an `ErrorEvent` instead,
        so a mid-stream failure still reaches SSE clients as a well-formed frame.
        """
        raise NotImplementedError
        yield TokenEvent(
            token=""
        )  # pragma: no cover — unreachable; keeps this an async generator for typing
