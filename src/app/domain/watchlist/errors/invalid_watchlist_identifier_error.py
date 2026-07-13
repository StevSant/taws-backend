class InvalidWatchlistIdentifierError(Exception):
    """Raised when a watchlist or item identifier isn't a well-formed value.

    Watchlist/item ids are Postgres `uuid` columns, but the router accepts them as
    plain path `str`s. A malformed value (not a uuid) makes Postgres reject the query
    with `errcode = '22P02'` (invalid_text_representation), which the Supabase adapter
    translates into this domain error so the router never sees a raw Postgres code.
    Caught by the API layer and mapped to `422 Unprocessable Content` — the client sent
    a syntactically invalid identifier, not a missing resource.
    """

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or "Malformed watchlist identifier")
