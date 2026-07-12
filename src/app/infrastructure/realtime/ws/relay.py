import asyncio
import contextlib
import json
import logging
from typing import Any, Protocol

from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.infrastructure.realtime.ws.extract_function_calls import extract_function_calls
from app.infrastructure.realtime.ws.handle_function_call import (
    handle_realtime_function_call,
)
from app.infrastructure.realtime.ws.map_openai_event import map_openai_event
from app.infrastructure.realtime.ws.openai_events import CLIENT_INPUT_AUDIO_APPEND

logger = logging.getLogger(__name__)

# Absolute ceiling on a single relayed session, independent of the configured TTL, so a
# stuck/abandoned socket pair can never hold an OpenAI connection open forever.
_MAX_SESSION_SECONDS_CAP = 3600

# Browser -> proxy control message the relay understands specially; everything else that
# isn't audio is forwarded verbatim to OpenAI so the client can drive the session.
_BROWSER_AUDIO_TYPE = "audio"


class BrowserSocket(Protocol):
    # Parameter names mirror Starlette's `WebSocket` so a real `WebSocket` satisfies this
    # protocol structurally (pyright checks keyword-arg names on protocol methods).
    async def receive_json(self) -> dict[str, Any]: ...
    async def send_json(self, data: Any, mode: str = "text") -> None: ...
    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


class OpenAISocket(Protocol):
    def __aiter__(self) -> Any: ...
    async def send(self, data: str) -> None: ...
    async def close(self) -> None: ...


async def run_realtime_relay(
    browser: BrowserSocket,
    openai: OpenAISocket,
    container: Any,
    user: Any,
    settings: Settings,
) -> None:
    """Relay audio + events both ways between the browser socket and the OpenAI socket.

    Runs two pumps concurrently until either side ends:
    - browser -> OpenAI: `{type:"audio"}` becomes `input_audio_buffer.append`; any other
      client control message is forwarded verbatim so the browser can steer the session.
    - OpenAI -> browser: each event is mapped (`map_openai_event`) and forwarded; a
      `response.done` carrying function calls is intercepted and dispatched IN-PROCESS with
      the JWT `user.id` (`handle_realtime_function_call`), the results sent back to OpenAI,
      and `tool-call-started`/`tool-call-finished` notifications emitted to the browser.

    Lifecycle guarantees (the reason this is one coordinator): when EITHER pump finishes —
    browser disconnect, OpenAI stream end, error, or the max-duration cap — the other pump
    is cancelled and BOTH sockets are closed in `finally`, so no OpenAI socket is ever
    leaked. The whole relay is bounded by `min(ttl, cap)` via `asyncio.wait_for`.
    """
    max_seconds = min(settings.openai_realtime_ttl_seconds, _MAX_SESSION_SECONDS_CAP)
    try:
        await asyncio.wait_for(
            _run_pumps(browser, openai, container, user), timeout=max_seconds
        )
    except TimeoutError:
        logger.info("Realtime relay hit the %ss duration cap; closing.", max_seconds)
    finally:
        await _close_quietly(openai.close())
        await _close_quietly(browser.close())


async def _run_pumps(
    browser: BrowserSocket, openai: OpenAISocket, container: Any, user: Any
) -> None:
    """Run both pumps; when the first finishes, cancel the other (first-to-finish wins).

    The two pump tasks are ALWAYS cancelled in `finally`, so if this coroutine is itself
    cancelled mid-`await` — e.g. by the `asyncio.wait_for` duration cap in
    `run_realtime_relay` — the still-running pump tasks are torn down deterministically
    instead of leaking (which would keep the OpenAI socket alive past the cap).
    """
    to_openai = asyncio.ensure_future(_pump_browser_to_openai(browser, openai))
    to_browser = asyncio.ensure_future(
        _pump_openai_to_browser(browser, openai, container, user)
    )
    tasks = (to_openai, to_browser)
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        # Surface a non-cancellation error from whichever pump finished first.
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.warning("Realtime relay pump ended with error: %r", exc)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _pump_browser_to_openai(browser: BrowserSocket, openai: OpenAISocket) -> None:
    """Forward browser messages to OpenAI until the browser disconnects.

    A malformed (non-JSON) browser frame surfaces as a `JSONDecodeError`/`ValueError` from
    `receive_json`; it is logged and SKIPPED so one bad frame can't kill the whole session —
    the pump keeps going and the next valid frame is still forwarded.
    """
    while True:
        try:
            message = await browser.receive_json()
        except WebSocketDisconnect:
            return
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.debug("Skipping malformed browser message", exc_info=True)
            continue
        if message.get("type") == _BROWSER_AUDIO_TYPE:
            await openai.send(
                json.dumps(
                    {"type": CLIENT_INPUT_AUDIO_APPEND, "audio": message.get("data", "")}
                )
            )
        else:
            # Forward other client control events verbatim (e.g. response.create,
            # input_audio_buffer.commit) so the browser can drive the session.
            await openai.send(json.dumps(message))


async def _pump_openai_to_browser(
    browser: BrowserSocket, openai: OpenAISocket, container: Any, user: Any
) -> None:
    """Map OpenAI events to the browser and intercept function calls server-side."""
    async for raw in openai:
        event = _loads(raw)
        if event is None:
            continue

        client_message = map_openai_event(event)
        if client_message is not None:
            await browser.send_json(client_message)

        for call in extract_function_calls(event):
            await _run_tool_call(browser, openai, container, user, call)


async def _run_tool_call(
    browser: BrowserSocket,
    openai: OpenAISocket,
    container: Any,
    user: Any,
    call: dict[str, Any],
) -> None:
    await browser.send_json(
        {"type": "tool-call-started", "name": call["name"], "call_id": call["call_id"]}
    )
    messages = await handle_realtime_function_call(
        container,
        name=call["name"],
        call_id=call["call_id"],
        arguments=call["arguments"],
        user_id=user.id,
    )
    for message in messages:
        await openai.send(json.dumps(message))
    await browser.send_json(
        {"type": "tool-call-finished", "name": call["name"], "call_id": call["call_id"]}
    )


def _loads(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def _close_quietly(close_coro: Any) -> None:
    with contextlib.suppress(Exception):
        await close_coro
