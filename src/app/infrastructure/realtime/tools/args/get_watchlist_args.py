from pydantic import BaseModel


class GetWatchlistArgs(BaseModel):
    """Validated arguments for the `get_watchlist` realtime tool.

    Takes no arguments: the watchlists returned are always the caller's own, scoped by the
    JWT-derived `user_id` in the handler — NEVER by any id supplied in the tool call. Extra
    fields are rejected so a hallucinated/compromised model call can't smuggle a `user_id`
    (or anything else) through to the backend.
    """

    model_config = {"extra": "forbid"}
