from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from app.domain.agents.ports import AgentMemory


class InMemoryCheckpointer(AgentMemory):
    """AgentMemory adapter backed by LangGraph's in-memory `MemorySaver`.

    This is the automatic fallback used by the DI container whenever
    `settings.redis_url` is unset — local/offline dev never breaks.
    """

    def __init__(self) -> None:
        self._checkpointer = MemorySaver()

    def get_checkpointer(self) -> Any:
        return self._checkpointer
