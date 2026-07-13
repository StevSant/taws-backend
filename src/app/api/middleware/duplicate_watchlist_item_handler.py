from fastapi import Request, status
from fastapi.responses import JSONResponse


async def duplicate_watchlist_item_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map `DuplicateWatchlistItemError` to `409 Conflict` with a human-readable detail.

    Registered app-wide (`main.create_app`) rather than as a per-endpoint `try/except`:
    only `SupabaseWatchlistRepository.add_item` raises this error, but registering once
    keeps the mapping in a single place and the router free of error-handling noise.
    """
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})
