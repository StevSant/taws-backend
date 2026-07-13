class MarketDataUnavailableError(RuntimeError):
    """Raised when no REAL price data can be obtained for an instrument.

    The market-data path has exactly two honest outcomes: real prices, or this error.
    There is deliberately no third option — no synthetic series, no cached-and-stale
    guess, no zero-filled placeholder. A fabricated price is strictly worse than a
    missing one here: every consumer downstream (chart rendering, `ComputeMarketStats`,
    the impact/confidence classification in `GenerateSignal`, and ultimately an
    investment recommendation shown to a user) treats whatever it receives as fact, so a
    plausible-looking invented number propagates silently all the way to the user as
    financial advice.

    This is not hypothetical: a keyless CoinGecko 429 once caused a fixture provider to
    serve a sha256-seeded random walk, and BTC was charted to a user at $333.6 (-11.15%)
    while it traded near $63,000. Nothing in the stack could tell the difference, because
    the fake series had the same shape as a real one.

    Callers must surface unavailability rather than paper over it: agent tools tell the
    model the data is unavailable (so it says so instead of inventing a number), and the
    API layer maps this to a 503.
    """

    def __init__(self, symbol: str, reason: str | None = None) -> None:
        self.symbol = symbol
        self.reason = reason
        detail = f": {reason}" if reason else ""
        super().__init__(f"No real market data available for {symbol}{detail}")
