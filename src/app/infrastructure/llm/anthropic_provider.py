from collections.abc import AsyncIterator
from typing import Any

from app.domain.agents.entities import Message
from app.domain.agents.ports import LLMProvider

_NOT_IMPLEMENTED_MESSAGE = "AnthropicProvider is a swap-point stub; implement to enable."


class AnthropicProvider(LLMProvider):
    """Swap-point stub demonstrating how to add a second `LLMProvider` adapter.

    Not implemented for the hackathon skeleton. To enable: add the Anthropic SDK
    dependency, build an `AsyncAnthropic` client here, implement `complete`/`stream`/
    `complete_structured`, and bind this class instead of `OpenAIProvider` in
    `core/di/container.py` — no other code needs to change.
    """

    def __init__(self, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def complete(self, messages: list[Message]) -> str:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)
        yield ""  # pragma: no cover — unreachable; keeps this an async generator for typing

    async def complete_structured(
        self, messages: list[Message], schema: dict[str, Any], schema_name: str
    ) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)
