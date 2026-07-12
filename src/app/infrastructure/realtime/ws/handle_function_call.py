import json
import logging
from typing import Any

from app.infrastructure.realtime.tools import dispatch_realtime_tool
from app.infrastructure.realtime.ws.openai_events import (
    CLIENT_CONVERSATION_ITEM_CREATE,
    CLIENT_RESPONSE_CREATE,
    ITEM_TYPE_FUNCTION_CALL_OUTPUT,
)

logger = logging.getLogger(__name__)


async def handle_realtime_function_call(
    container: Any,
    *,
    name: str,
    call_id: str,
    arguments: dict[str, Any],
    user_id: str,
) -> list[dict[str, Any]]:
    """Run one model-requested tool call server-side and return the OpenAI reply messages.

    Reuses the in-process registry (`dispatch_realtime_tool`) — the proxy never self-HTTPs
    to `/realtime/tool`. Security mirrors that endpoint:
    - `name` is allowlisted and `arguments` schema-validated inside `dispatch_realtime_tool`
      (unknown tool / bad args raise, caught below).
    - the acting `user_id` is the verified JWT subject, passed positionally — NEVER read
      from `arguments` (a malicious `arguments.user_id` is ignored).

    Always returns two messages to send back to OpenAI, in order:
    `[conversation.item.create{function_call_output, call_id, output}, response.create]`.
    On ANY tool failure the `output` is a structured `{"error": ...}` string instead of
    raising, so the voice model recovers verbally rather than the turn dropping.
    """
    try:
        output = await dispatch_realtime_tool(container, name, arguments, user_id)
    except Exception as exc:  # noqa: BLE001 — recoverable tool error, not a server fault
        logger.warning("Realtime WS tool %r failed for call %r", name, call_id, exc_info=True)
        output = {"error": str(exc)}

    return [
        {
            "type": CLIENT_CONVERSATION_ITEM_CREATE,
            "item": {
                "type": ITEM_TYPE_FUNCTION_CALL_OUTPUT,
                "call_id": call_id,
                "output": json.dumps(output),
            },
        },
        {"type": CLIENT_RESPONSE_CREATE},
    ]
