import json
from typing import Any

from app.infrastructure.realtime.ws.openai_events import (
    ITEM_TYPE_FUNCTION_CALL,
    OPENAI_RESPONSE_DONE,
)


def extract_function_calls(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull any `function_call` items out of a `response.done` event.

    Returns a list of `{"name", "call_id", "arguments"}` dicts (arguments parsed from the
    JSON string OpenAI sends), or `[]` when the event isn't a `response.done` or carries no
    function calls. Pure — tested with plain dicts. Malformed argument JSON degrades to
    `{}` so a single bad tool call can't crash the relay (the tool's arg validation then
    rejects it and the model recovers).
    """
    if event.get("type") != OPENAI_RESPONSE_DONE:
        return []
    output = (event.get("response") or {}).get("output") or []
    calls: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != ITEM_TYPE_FUNCTION_CALL:
            continue
        calls.append(
            {
                "name": item.get("name", ""),
                "call_id": item.get("call_id", ""),
                "arguments": _parse_arguments(item.get("arguments")),
            }
        )
    return calls


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
