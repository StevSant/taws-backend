import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: unexpected errors return clean JSON, never a raw stack trace.

    The client only ever sees an opaque 500, so the underlying cause is logged with the
    exception type, message, and — for PostgREST/Postgres failures (`.code`, e.g. `42501`
    RLS rejection or `42P01` missing table) — the DB error code, making genuine server
    errors diagnosable from the logs (issue #22). Domain errors that map to specific
    statuses (409/422) are handled by their own registered handlers before reaching here.
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
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})
