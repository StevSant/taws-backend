class InsufficientEvidenceError(RuntimeError):
    """Raised when no news evidence at all is available to ground a signal.

    Never resolved by fabricating evidence — see `GenerateSignal._gather_news` in
    `generate_signal.py`, which only ever broadens the search to real, sourced/dated news.
    """

    def __init__(self, symbol: str) -> None:
        super().__init__(f"No news evidence available to generate a signal for {symbol!r}")
        self.symbol = symbol
