from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

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

    @abstractmethod
    async def complete_structured(
        self, messages: list[Message], schema: dict[str, Any], schema_name: str
    ) -> dict[str, Any]:
        """Return one JSON object matching `schema`, for classification/extraction-style
        calls (e.g. the Analyst pipeline's news-impact classification).

        `schema` is a plain JSON Schema `dict` — typically a Pydantic model's
        `.model_json_schema()` — and `schema_name` is a short identifier passed through
        to vendor structured-output APIs that need one (OpenAI's
        `response_format.json_schema.name`). This port only deals in plain `dict`s so
        `domain/`/`application/` never need a vendor SDK (or LangChain) import to use
        structured output — callers own schema definition and result validation
        (typically `SomeModel.model_validate(result)`).

        Implementations must raise rather than silently return a malformed/empty dict
        when structured output isn't available (e.g. no API key configured) — callers
        are expected to catch broadly and degrade gracefully, the same way
        `application/signals/use_cases/generate_signal.py` does around this call.

        Raise `LLMProviderUnavailableError` specifically for a *permanent* unavailability
        that no retry can fix (e.g. no API key configured); raise ordinary exceptions for
        *transient* failures (rate limits, timeouts, malformed/unparseable structured
        output) so callers can distinguish "fall back now" from "retry, then fall back".
        """
        raise NotImplementedError
