from typing import Any

from app.domain.agents.ports import AgentMemory


class RedisCheckpointer(AgentMemory):
    """AgentMemory adapter backed by Redis (Upstash) via a LangGraph checkpointer.

    Built lazily: `get_checkpointer()` constructs the `RedisSaver` and runs its
    `setup()` (which creates the required RedisJSON/RediSearch indices) on first
    use. If the server does not support those modules (some managed Redis
    providers don't) or the URL is wrong, this raises — the DI container catches
    that and falls back to `InMemoryCheckpointer`, so chat never breaks on a
    Redis problem.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._checkpointer: Any | None = None

    def get_checkpointer(self) -> Any:
        if self._checkpointer is None:
            self._checkpointer = self._build_checkpointer()
        return self._checkpointer

    def _build_checkpointer(self) -> Any:
        from langgraph.checkpoint.redis import RedisSaver

        saver = RedisSaver(redis_url=self._redis_url)
        saver.setup()
        return saver
