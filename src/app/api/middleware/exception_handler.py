import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.middleware.cors_headers import build_cors_headers_for_origin
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: unexpected errors return clean JSON, never a raw stack trace.

    The client only ever sees an opaque 500, so the underlying cause is logged with the
    exception type, message, and — for PostgREST/Postgres failures (`.code`, e.g. `42501`
    RLS rejection or `42P01` missing table) — the DB error code, making genuine server
    errors diagnosable from the logs (issue #22). Domain errors that map to specific
    statuses (409/422) are handled by their own registered handlers before reaching here.

    This handler runs in `ServerErrorMiddleware`, which is *outside* `CORSMiddleware`, so
    the 500 response would otherwise ship without `Access-Control-Allow-Origin` and the
    browser would surface a misleading CORS error instead of the real 500. We reattach the
    allow-listed CORS headers here (echoing the request Origin only when it is on the
    configured allow-list) so cross-origin clients see the actual status.
    """
    postgrest_code = getattr(exc, "code", None)
    logger.exception(
        "Unhandled exception while processing %s %s: %s: %s (db_code=%s)",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
        postgrest_code,
    )
    cors_headers = build_cors_headers_for_origin(request.headers.get("origin"), get_settings())
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
        headers=cors_headers,
    )
