from fastapi import Request, status
from fastapi.responses import JSONResponse


async def invalid_watchlist_identifier_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map `InvalidWatchlistIdentifierError` to `422 Unprocessable Content`.

    A malformed (non-uuid) watchlist/item id is a bad request payload, not a missing
    resource — so 422, not 404 or 500. Registered app-wide (`main.create_app`); the
    detail is a fixed, safe message (never the raw Postgres text) to avoid leaking DB
    internals to the client.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "Malformed watchlist identifier."},
    )
