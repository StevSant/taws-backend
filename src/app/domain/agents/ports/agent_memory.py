from abc import ABC, abstractmethod
from typing import Any


class AgentMemory(ABC):
    """Port for per-thread agent conversation state (a LangGraph checkpointer).

    The return type is intentionally `Any`: the domain layer must stay pure and may
    not import LangGraph. Adapters return a LangGraph-compatible checkpointer
    instance (e.g. `MemorySaver`, a Redis-backed saver) that the infrastructure
    graph-building code knows how to consume.
    """

    @abstractmethod
    def get_checkpointer(self) -> Any:
        """Return the underlying checkpointer instance for this adapter."""
        raise NotImplementedError
