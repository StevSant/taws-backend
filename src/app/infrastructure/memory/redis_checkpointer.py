from typing import Any

from app.domain.agents.ports import AgentMemory


class RedisCheckpointer(AgentMemory):
    """AgentMemory adapter backed by Redis (Upstash) via a LangGraph checkpointer.

    Built lazily on purpose: `langgraph-checkpoint-redis` is an optional dependency
    not installed by default in this skeleton. Importing this module always
    succeeds; only `get_checkpointer()` needs the package, and only once the DI
    container has already decided (via `settings.redis_url`) to use Redis at all.
    Install with `uv add langgraph-checkpoint-redis` to enable it for real.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._checkpointer: Any | None = None

    def get_checkpointer(self) -> Any:
        if self._checkpointer is None:
            self._checkpointer = self._build_checkpointer()
        return self._checkpointer

    def _build_checkpointer(self) -> Any:
        try:
            from langgraph.checkpoint.redis import (  # pyright: ignore[reportMissingImports]
                RedisSaver,
            )
        except ImportError as exc:
            raise RuntimeError(
                "RedisCheckpointer requires the optional 'langgraph-checkpoint-redis' "
                "package. Install it with `uv add langgraph-checkpoint-redis`, or "
                "unset REDIS_URL to use the InMemoryCheckpointer fallback instead."
            ) from exc

        return RedisSaver.from_conn_string(self._redis_url)
