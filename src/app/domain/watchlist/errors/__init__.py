"""Watchlist domain errors: raised by adapters, mapped to HTTP status by the API layer."""

from app.domain.watchlist.errors.duplicate_watchlist_item_error import (
    DuplicateWatchlistItemError,
)
from app.domain.watchlist.errors.invalid_watchlist_identifier_error import (
    InvalidWatchlistIdentifierError,
)

__all__ = ["DuplicateWatchlistItemError", "InvalidWatchlistIdentifierError"]
