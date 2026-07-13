from app.core.config import Settings


def build_cors_headers_for_origin(origin: str | None, settings: Settings) -> dict[str, str]:
    """Return the CORS headers to attach to a response for a given request Origin.

    Starlette's `CORSMiddleware` only decorates responses that flow through it normally.
    A 500 raised into the global exception handler is produced by `ServerErrorMiddleware`,
    which sits *outside* `CORSMiddleware`, so that JSON response never gets an
    `Access-Control-Allow-Origin` header — the browser then masks the real 500 as a CORS
    error. This helper reconstructs the same allow-listed, credentialed CORS headers the
    middleware would have added, so the exception handler can attach them by hand.

    Origins are read from `Settings.cors_origins` (no literals — see backend/CLAUDE.md's
    no-hardcoded-values rule). The request Origin is echoed back only when it is on the
    allow-list; we never emit a wildcard `*` alongside credentials, which browsers reject.
    """
    if origin is None or origin not in settings.cors_origins:
        return {}

    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }
