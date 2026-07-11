class UnknownInstrumentError(ValueError):
    """Raised when a requested instrument symbol isn't in the curated universe."""

    def __init__(self, symbol: str) -> None:
        super().__init__(f"Unknown instrument symbol: {symbol!r}")
        self.symbol = symbol
