class UnknownInstrumentError(ValueError):
    """Raised when a requested instrument symbol isn't in the curated universe.

    Deliberately a separate class from `application.signals.UnknownInstrumentError`
    (same shape) rather than an import across feature packages, so `application/quant`
    stays self-contained and importable on its own by a future caller (e.g. issue #12's
    Scenario Simulation graph) without pulling in the Analyst/signals slice.
    """

    def __init__(self, symbol: str) -> None:
        super().__init__(f"Unknown instrument symbol: {symbol!r}")
        self.symbol = symbol
