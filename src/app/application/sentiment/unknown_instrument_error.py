class UnknownInstrumentError(ValueError):
    """Raised when a requested instrument symbol isn't in the curated universe.

    Deliberately a separate class from `application.signals.UnknownInstrumentError`/
    `application.quant.UnknownInstrumentError` (same shape) rather than an import across
    feature packages, so `application/sentiment` stays self-contained — see
    `application/quant/unknown_instrument_error.py`'s docstring for the established
    rationale this mirrors.
    """

    def __init__(self, symbol: str) -> None:
        super().__init__(f"Unknown instrument symbol: {symbol!r}")
        self.symbol = symbol
