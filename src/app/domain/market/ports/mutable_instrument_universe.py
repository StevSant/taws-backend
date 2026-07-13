from typing import Protocol, runtime_checkable

from app.domain.market.entities import Instrument, InstrumentRow


@runtime_checkable
class MutableInstrumentUniverse(Protocol):
    """Structural port for appending a newly registered instrument to the universe.

    Deliberately a `Protocol`, not an `InstrumentUniverse` ABC method (design
    decision #7): `InstrumentUniverse`'s ~15 existing consumers only ever read
    (`all`/`by_symbol`/`by_asset_class`), so widening that ABC would force every
    read-only fake/adapter to also implement `add`. `RegisterInstrument` (Slice 2)
    depends on THIS protocol instead, so it can never accidentally depend on a
    concrete `SupabaseInstrumentUniverse` type or reach for `isinstance`.

    `add_row()` (CRITICAL fix, post-hoc adversarial review) appends the FULL raw
    `InstrumentRow` — including `coingecko_id`/`yfinance_symbol` — instead of the
    vendor-id-free `Instrument` entity `add()` takes. `RegisterInstrument` must call
    `add_row()`, not `add()`, so a newly registered coin's vendor id is not silently
    dropped from the in-memory index and its live override maps.
    """

    def add(self, instrument: Instrument) -> None:
        """Append a newly registered instrument to the in-memory index."""
        ...

    def add_row(self, row: InstrumentRow) -> None:
        """Append a newly registered raw catalog row, preserving vendor-id overrides."""
        ...
