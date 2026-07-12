class UnknownInstrumentToolError(Exception):
    """Raised by a realtime tool handler when a symbol isn't in the curated universe.

    A recoverable, model-facing condition (not a server fault): the `/chat/realtime/tool`
    endpoint maps it to a structured error output so the voice model can apologize and
    ask for a valid symbol, rather than returning a 500.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"Unknown instrument: {symbol}")
