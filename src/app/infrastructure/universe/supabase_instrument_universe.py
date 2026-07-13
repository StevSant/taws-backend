from typing import Self

from app.domain.market.entities import AssetClass, Instrument, InstrumentRow
from app.domain.market.ports import InstrumentCatalogRepository, InstrumentUniverse


class SupabaseInstrumentUniverse(InstrumentUniverse):
    """InstrumentUniverse adapter backed by the global `public.instruments` table.

    The `InstrumentUniverse` port stays SYNCHRONOUS (design decision #1): the DB
    read only happens once, in the async `create()` factory (awaited in the FastAPI
    `_lifespan` hook and cached as the `Container` singleton) — `all()`,
    `by_symbol()`, and `by_asset_class()` are then plain in-memory lookups — exactly
    like the previous `JsonInstrumentUniverse` seed-file adapter it replaces. This
    keeps every existing consumer (`~15` call sites) behavior-preserving with zero
    ripple.

    `add()` (FIX #6, append-on-register) and `all_rows()` (FIX #7, sync vendor-id
    override source for `get_market_data_provider`) are adapter-only additions on
    top of the `InstrumentUniverse` ABC — `add()` also satisfies the domain
    `MutableInstrumentUniverse` protocol structurally.
    """

    def __init__(self, rows: list[InstrumentRow]) -> None:
        self._rows: dict[str, InstrumentRow] = {row.symbol.upper(): row for row in rows}
        self._instruments: dict[str, Instrument] = {
            symbol: _instrument_from_row(row) for symbol, row in self._rows.items()
        }

    @classmethod
    async def create(cls, repo: InstrumentCatalogRepository) -> Self:
        """Load the whole catalog once from `repo` and build the in-memory index."""
        rows = await repo.all_rows()
        if not rows:
            raise RuntimeError(
                "instruments catalog is empty — run migration 0012 against the "
                "configured database (the DB-backed universe never boots a "
                "silent-empty catalog)"
            )
        return cls(rows)

    def all(self) -> list[Instrument]:
        return list(self._instruments.values())

    def by_symbol(self, symbol: str) -> Instrument | None:
        return self._instruments.get(symbol.upper())

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [
            instrument
            for instrument in self._instruments.values()
            if instrument.asset_class == asset_class
        ]

    def add(self, instrument: Instrument) -> None:
        """Append a newly registered instrument to the in-memory index (idempotent)."""
        symbol = instrument.symbol.upper()
        self._instruments[symbol] = instrument
        self._rows[symbol] = InstrumentRow(
            symbol=instrument.symbol,
            name=instrument.name,
            asset_class=instrument.asset_class,
            currency=instrument.currency,
        )

    def all_rows(self) -> list[InstrumentRow]:
        """Return every raw catalog row, including vendor-id overrides.

        Sync accessor over the already-built in-memory index (FIX #7) — used by
        `get_market_data_provider` to build the CoinGecko/yfinance override maps
        without a fresh async DB read.
        """
        return list(self._rows.values())


def _instrument_from_row(row: InstrumentRow) -> Instrument:
    """Map a raw catalog row onto the pure `Instrument` entity, dropping vendor ids."""
    return Instrument(
        symbol=row.symbol,
        name=row.name,
        asset_class=row.asset_class,
        currency=row.currency,
    )
