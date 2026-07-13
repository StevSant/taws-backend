class FundamentalsUnavailableError(RuntimeError):
    """Raised when real fundamentals (or a real earnings date) can't be fetched for a symbol.

    Same rule as [`MarketDataUnavailableError`][app.domain.market.errors]: real numbers or an
    error. An invented P/E or a made-up earnings date reads exactly like a real one, and both
    feed straight into the analyst's thesis.
    """

    def __init__(self, symbol: str, reason: str | None = None) -> None:
        self.symbol = symbol
        self.reason = reason
        detail = f": {reason}" if reason else ""
        super().__init__(f"No real fundamentals available for {symbol}{detail}")
