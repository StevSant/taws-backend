class InsufficientEvidenceError(RuntimeError):
    """Raised when a signal doesn't meet the minimum news-evidence floor.

    Covers both triggers checked in `GenerateSignal.execute` (`generate_signal.py`):
    - No news evidence at all (`_gather_news` returned zero items).
    - Fewer than `_MIN_DISTINCT_SOURCES` distinct sources even after `_gather_news` broadens
      the search to asset-class context — HU1's acceptance criterion requires "≥2 news
      sources with source + date visible per signal card", so a signal grounded in only one
      distinct source must not be persisted either.

    Never resolved by fabricating evidence — `_gather_news` only ever broadens the search to
    real, sourced/dated news; if the floor still isn't met after broadening, generation is
    aborted instead of persisting a thinly-sourced signal.
    """

    def __init__(self, symbol: str, distinct_sources: int | None = None) -> None:
        if distinct_sources is None:
            message = f"No news evidence available to generate a signal for {symbol!r}"
        else:
            message = (
                f"Only {distinct_sources} distinct news source(s) available for {symbol!r}; "
                "at least 2 are required to generate a signal"
            )
        super().__init__(message)
        self.symbol = symbol
        self.distinct_sources = distinct_sources
