import json
from collections.abc import AsyncIterator
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema

from app.domain.agents.entities import Message
from app.domain.agents.ports import LLMProvider

_NO_KEY_MESSAGE = (
    "[OpenAIProvider] No OPENAI_API_KEY configured — this is a placeholder response "
    "so the chat stream keeps working without a real key."
)
_NO_KEY_STRUCTURED_ERROR = (
    "[OpenAIProvider] No OPENAI_API_KEY configured — structured output unavailable."
)
_EMPTY_STRUCTURED_RESPONSE_ERROR = "[OpenAIProvider] Structured output response had no content."


def _to_openai_messages(messages: list[Message]) -> list[ChatCompletionMessageParam]:
    """Adapt domain Messages to the OpenAI SDK's expected message param shape."""
    return cast(
        list[ChatCompletionMessageParam],
        [{"role": message.role.value, "content": message.content} for message in messages],
    )


class OpenAIProvider(LLMProvider):
    """LLMProvider adapter backed by the OpenAI Chat Completions API.

    Guarded so the app never crashes when `OPENAI_API_KEY` is unset: `complete()`
    and `stream()` fall back to a canned placeholder in that case.
    """

    def __init__(self, api_key: str | None, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None
        self._model = model

    async def complete(self, messages: list[Message]) -> str:
        if self._client is None:
            return _NO_KEY_MESSAGE

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=_to_openai_messages(messages),
        )
        return response.choices[0].message.content or ""

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        if self._client is None:
            for word in _NO_KEY_MESSAGE.split(" "):
                yield f"{word} "
            return

        completion_stream = await self._client.chat.completions.create(
            model=self._model,
            messages=_to_openai_messages(messages),
            stream=True,
        )
        async for chunk in completion_stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def complete_structured(
        self, messages: list[Message], schema: dict[str, Any], schema_name: str
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError(_NO_KEY_STRUCTURED_ERROR)

        response_format = cast(
            ResponseFormatJSONSchema,
            {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": False},
            },
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=_to_openai_messages(messages),
            response_format=response_format,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError(_EMPTY_STRUCTURED_RESPONSE_ERROR)
        return cast(dict[str, Any], json.loads(content))
