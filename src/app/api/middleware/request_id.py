import logging
import uuid
from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """Pure-ASGI request-lifecycle middleware: correlation id + one timing log per request.

    Two responsibilities, both tied to a single request's lifecycle:

    - **Request id.** Reuse an inbound `X-Request-ID` header or mint a UUID4, expose it on
      `scope["state"]["request_id"]` (so `request.state.request_id` still resolves), and echo
      it back on the response's `X-Request-ID` header — unchanged from the previous version.
    - **Timing.** For `http` requests, log exactly one INFO line
      (`request_id method path status duration_ms`) when the terminal response body frame is
      flushed, or when the app raises before completing. Per-token `http.response.body` frames
      with `more_body=True` are not logged, so a streaming (SSE) reply still logs once.

    Implemented at the raw ASGI layer rather than Starlette's `BaseHTTPMiddleware` on purpose:
    `BaseHTTPMiddleware` pumps the response through an anyio memory stream, which buffers and
    interferes with token-by-token SSE flushing; a thin `send` wrapper does not. Non-`http`
    scopes (`websocket`, `lifespan`) are passed straight through untouched.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = Headers(scope=scope).get(_REQUEST_ID_HEADER, str(uuid.uuid4()))
        scope.setdefault("state", {})["request_id"] = request_id

        started_at = perf_counter()
        # Mutable across the send closure and the except branch: the captured status and a
        # once-only guard so a request is never logged twice (terminal frame *and* exception).
        response_status = 0
        logged = False

        async def wrapped_send(message: Message) -> None:
            nonlocal response_status, logged
            if message["type"] == "http.response.start":
                response_status = message["status"]
                MutableHeaders(scope=message)[_REQUEST_ID_HEADER] = request_id
            await send(message)
            terminal_body = message["type"] == "http.response.body" and not message.get(
                "more_body", False
            )
            if terminal_body and not logged:
                logged = True
                self._log_completion(scope, request_id, response_status, started_at)

        try:
            await self._app(scope, receive, wrapped_send)
        except Exception:
            if not logged:
                logged = True
                # No `http.response.start` may have been sent, so fall back to 500.
                self._log_completion(scope, request_id, response_status or 500, started_at)
            raise

    def _log_completion(
        self, scope: Scope, request_id: str, status: int, started_at: float
    ) -> None:
        duration_ms = round((perf_counter() - started_at) * 1000)
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            scope["method"],
            scope["path"],
            status,
            duration_ms,
        )
