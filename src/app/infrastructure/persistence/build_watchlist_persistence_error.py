from supabase import PostgrestAPIError

from app.domain.watchlist.errors import (
    DuplicateWatchlistItemError,
    InvalidWatchlistIdentifierError,
)

_UNIQUE_VIOLATION_CODE = "23505"
_INVALID_TEXT_REPRESENTATION_CODE = "22P02"


def build_watchlist_persistence_error(
    exc: PostgrestAPIError, *, symbol: str | None = None
) -> DuplicateWatchlistItemError | InvalidWatchlistIdentifierError | None:
    """Translate a PostgREST error into a watchlist domain error, or `None`.

    Keeps the hexagonal boundary clean: `SupabaseWatchlistRepository` calls this on any
    `PostgrestAPIError` and re-raises the returned domain error, so routers map on
    domain types (409/422) instead of ever seeing a Postgres error code. Returns `None`
    for any other code — callers re-raise the original `exc` unchanged so genuine
    server errors still reach the catch-all handler (and its 500 + log).

    - `23505` unique_violation → `DuplicateWatchlistItemError` (re-adding a tracked
      symbol; the `watchlist_items` `unique (watchlist_id, symbol)` constraint). `symbol`
      is threaded through for a human-readable message when known.
    - `22P02` invalid_text_representation → `InvalidWatchlistIdentifierError` (a path
      param that isn't a well-formed uuid).

    `PostgrestAPIError` is imported from the top-level `supabase` package (which
    re-exports it), matching `build_illegal_review_transition_error` — `postgrest` isn't
    a direct dependency.
    """
    if exc.code == _UNIQUE_VIOLATION_CODE:
        return DuplicateWatchlistItemError(symbol or "")
    if exc.code == _INVALID_TEXT_REPRESENTATION_CODE:
        return InvalidWatchlistIdentifierError(exc.message)
    return None
