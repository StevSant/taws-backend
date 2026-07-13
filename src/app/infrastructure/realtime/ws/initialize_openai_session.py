import json
from typing import Any

from app.core.config import Settings
from app.infrastructure.realtime.ws.build_realtime_session_update import (
    build_realtime_session_update,
)
from app.infrastructure.realtime.ws.openai_events import OPENAI_SESSION_CREATED


async def initialize_openai_session(openai: Any, settings: Settings) -> None:
    """Wait for OpenAI's `session.created`, then send the server-authored `session.update`.

    The Realtime API emits `session.created` once the socket is ready; the proxy must not
    configure the session (tools/instructions/audio format) before then. Consumes leading
    events until `session.created` arrives, sends exactly one `session.update`, and returns
    (the relay then takes over the socket). If the stream ends before `session.created`
    (connection dropped during handshake), sends nothing — the relay's cleanup closes the
    sockets.
    """
    async for raw in openai:
        event = _loads(raw)
        if event is not None and event.get("type") == OPENAI_SESSION_CREATED:
            await openai.send(json.dumps(build_realtime_session_update(settings)))
            return


def _loads(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None
