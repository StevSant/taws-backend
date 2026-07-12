from typing import Protocol, runtime_checkable

from app.domain.market.entities import Instrument


@runtime_checkable
class MutableInstrumentUniverse(Protocol):
    """Structural port for appending a newly registered instrument to the universe.

    Deliberately a `Protocol`, not an `InstrumentUniverse` ABC method (design
    decision #7): `InstrumentUniverse`'s ~15 existing consumers only ever read
    (`all`/`by_symbol`/`by_asset_class`), so widening that ABC would force every
    read-only fake/adapter to also implement `add`. `RegisterInstrument` (Slice 2)
    depends on THIS protocol instead, so it can never accidentally depend on a
    concrete `SupabaseInstrumentUniverse` type or reach for `isinstance`.
    """

    def add(self, instrument: Instrument) -> None:
        """Append a newly registered instrument to the in-memory index."""
        ...
