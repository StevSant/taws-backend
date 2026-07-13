from app.domain.market.entities import Instrument


class SymbolCollisionError(RuntimeError):
    """Raised by `RegisterInstrument` when `symbol` already exists under a
    DIFFERENT asset class than the one being registered (always `CRYPTO` today).

    The router maps this to HTTP 409 with the `existing_instrument` in the body
    (instrument-registration spec: "ticker collides with an existing stock
    symbol" — the existing row is NOT overwritten or mutated, no write happens).
    """

    def __init__(self, symbol: str, existing_instrument: Instrument) -> None:
        super().__init__(
            f"Symbol {symbol!r} already exists as {existing_instrument.asset_class.value!r}"
        )
        self.symbol = symbol
        self.existing_instrument = existing_instrument
