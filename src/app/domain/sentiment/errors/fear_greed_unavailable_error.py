class FearGreedUnavailableError(RuntimeError):
    """Raised when a real Fear & Greed reading can't be fetched from the live index.

    Same rule as [`MarketDataUnavailableError`][app.domain.market.errors]: a real reading or
    an error. A fixture reading is a fabricated claim about how the entire market currently
    feels — rendered to the user as a gauge, which reads as measurement, not as a guess.
    """

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason
        detail = f": {reason}" if reason else ""
        super().__init__(f"No real Fear & Greed reading available{detail}")
