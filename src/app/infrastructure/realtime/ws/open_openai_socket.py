import hashlib
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from app.core.config import Settings
from app.infrastructure.realtime.ws.openai_events import OPENAI_REALTIME_WS_URL


def resolve_realtime_api_key(settings: Settings) -> str | None:
    """The billed Realtime key, falling back to the plain OpenAI key (mirrors the DI gate).

    Prefers the dedicated `openai_realtime_api_key` so realtime audio can be scoped/rotated
    independently, but falls back to `openai_api_key` so a single key can drive both chat
    and voice. `None` when neither is set — the endpoint then closes the socket unconfigured.
    """
    return settings.openai_realtime_api_key or settings.openai_api_key


def build_openai_realtime_url(model: str) -> str:
    """`wss://api.openai.com/v1/realtime?model=<model>` — the model is a query param."""
    return f"{OPENAI_REALTIME_WS_URL}?{urlencode({'model': model})}"


async def open_openai_socket(settings: Settings, api_key: str, user_id: str) -> Any:
    """Open the server-side WebSocket to OpenAI's Realtime API.

    The real (billed) key travels only in this server->OpenAI `Authorization` header and
    NEVER reaches the browser. `OpenAI-Safety-Identifier` carries a non-reversible hash of
    the JWT user id for abuse tracing (same as the WebRTC mint path). This is the network
    seam — it needs a live OpenAI key + reachable endpoint to verify, so it is deliberately
    thin and kept out of the unit-tested relay/handshake logic. [VERIFY LIVE]
    """
    url = build_openai_realtime_url(settings.openai_realtime_model)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Safety-Identifier": _hash_user_id(user_id),
    }
    return await connect(url, additional_headers=headers)


def _hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()
