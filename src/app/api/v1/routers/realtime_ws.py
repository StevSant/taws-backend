import logging

from fastapi import APIRouter, Query, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.api.v1.dependencies import verify_realtime_ws_token
from app.core.config import get_settings
from app.core.di import get_container
from app.infrastructure.realtime.ws import (
    initialize_openai_session,
    open_openai_socket,
    resolve_realtime_api_key,
    run_realtime_relay,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat-realtime-ws"])

# WebSocket close codes (RFC 6455 + app-specific). 1008 = policy violation (auth); 1011 =
# internal error / unconfigured; 1013 = try again later (OpenAI connect failed).
_WS_POLICY_VIOLATION = 1008
_WS_INTERNAL_ERROR = 1011
_WS_TRY_AGAIN_LATER = 1013


@router.websocket("/realtime/ws")
async def realtime_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    """WebSocket voice-proxy transport: browser <-WSS-> backend <-WSS-> OpenAI Realtime.

    Works on ANY network (plain WSS over TCP/443 — no WebRTC/STUN/TURN/ICE). The browser
    streams base64 PCM16 audio here; this endpoint relays it to OpenAI's Realtime API over
    a server-side socket that carries the real (billed) key in its `Authorization` header —
    the key NEVER reaches the browser. Function calls are dispatched server-side with the
    JWT user id (see `run_realtime_relay`).

    Auth: a browser `WebSocket` can't set an `Authorization` header, so the Supabase JWT
    arrives as `?token=` and is verified (ES256/JWKS) by `verify_realtime_ws_token`; an
    invalid/missing token closes with 1008 before any OpenAI connection is opened. When the
    Realtime feature is unconfigured (no key), the socket is accepted then closed with 1011
    so the frontend can fall back. Both sockets are always closed on exit — no leaks.
    """
    settings = get_settings()

    user = verify_realtime_ws_token(token, settings)
    if user is None:
        await websocket.close(code=_WS_POLICY_VIOLATION)
        return

    if not settings.openai_realtime_enabled:
        await websocket.accept()
        await websocket.close(code=_WS_INTERNAL_ERROR)
        return
    api_key = resolve_realtime_api_key(settings)
    if not api_key:
        await websocket.accept()
        await websocket.close(code=_WS_INTERNAL_ERROR)
        return

    await websocket.accept()

    try:
        openai_socket = await open_openai_socket(settings, api_key, user.id)
    except Exception:  # noqa: BLE001 — connect failure must not 500; tell client to retry
        logger.warning("Failed to open OpenAI Realtime socket", exc_info=True)
        await websocket.close(code=_WS_TRY_AGAIN_LATER)
        return

    try:
        await initialize_openai_session(openai_socket, settings)
        await run_realtime_relay(
            websocket, openai_socket, get_container(), user, settings
        )
    except WebSocketDisconnect:
        # Browser hung up during handshake/relay; `run_realtime_relay` (or its absence
        # here) still owns socket cleanup below.
        await _close_openai_quietly(openai_socket)
    except Exception:  # noqa: BLE001 — never let a relay fault escape as an unhandled 500
        logger.warning("Realtime relay failed", exc_info=True)
        await _close_openai_quietly(openai_socket)
        await _close_browser_quietly(websocket)


async def _close_openai_quietly(openai_socket: object) -> None:
    close = getattr(openai_socket, "close", None)
    if close is None:
        return
    try:
        await close()
    except Exception:  # noqa: BLE001 — best-effort cleanup
        logger.debug("OpenAI socket close failed", exc_info=True)


async def _close_browser_quietly(websocket: WebSocket) -> None:
    try:
        await websocket.close(code=_WS_INTERNAL_ERROR)
    except Exception:  # noqa: BLE001 — best-effort cleanup
        logger.debug("Browser socket close failed", exc_info=True)
