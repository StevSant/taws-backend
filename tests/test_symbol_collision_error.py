"""`SymbolCollisionError`: raised by `RegisterInstrument` when a resolved symbol
already exists in the catalog under a DIFFERENT asset class (e.g. a crypto
registration colliding with an existing stock ticker like `COIN`).

Carries the colliding `symbol` and the `existing_instrument` so the router can
map it to a 409 response with the existing instrument in the body, per the
instrument-registration spec's "ticker collides with an existing stock symbol"
scenario.
"""

from app.application.instruments.errors import SymbolCollisionError
from app.domain.market.entities import AssetClass, Instrument

_EXISTING_STOCK = Instrument(
    symbol="COIN", name="Coinbase Global Inc.", asset_class=AssetClass.STOCK, currency="USD"
)


def test_symbol_collision_error_carries_symbol_and_existing_instrument() -> None:
    error = SymbolCollisionError(symbol="COIN", existing_instrument=_EXISTING_STOCK)

    assert error.symbol == "COIN"
    assert error.existing_instrument is _EXISTING_STOCK
    assert "COIN" in str(error)
