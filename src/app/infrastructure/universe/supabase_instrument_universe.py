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

    `add_row()` + `coingecko_id_overrides()`/`yfinance_symbol_overrides()` (CRITICAL
    fix, post-hoc adversarial review) close a gap `add()` alone could not: `add()`
    rebuilds a vendor-id-less `InstrumentRow` (`coingecko_id=None`), so a newly
    registered coin's id never reached `all_rows()`. Worse, `Container.
    get_market_data_provider` used to build its override dicts as a ONE-TIME
    snapshot from `all_rows()`, so even a correct row update would never reach the
    already-constructed, cached `CoinGeckoMarketDataProvider`. The override dicts
    below are built ONCE in `__init__` and mutated in place by `add_row()` — any
    caller (e.g. the DI container) holding a reference to the SAME dict object sees
    every subsequent registration live, with no rebuild and no restart required.
    """

    def __init__(self, rows: list[InstrumentRow]) -> None:
        self._rows: dict[str, InstrumentRow] = {row.symbol.upper(): row for row in rows}
        self._instruments: dict[str, Instrument] = {
            symbol: _instrument_from_row(row) for symbol, row in self._rows.items()
        }
        self._coingecko_overrides: dict[str, str] = {
            row.symbol: row.coingecko_id for row in rows if row.coingecko_id
        }
        self._yfinance_overrides: dict[str, str] = {
            row.symbol: row.yfinance_symbol for row in rows if row.yfinance_symbol
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

    def add_row(self, row: InstrumentRow) -> None:
        """Append a newly registered catalog row, preserving vendor-id overrides.

        Unlike `add(instrument)` (which only knows the vendor-id-free `Instrument`
        entity), this updates `_rows`/`_instruments` from the full `InstrumentRow`
        the caller already built (with `coingecko_id`/`yfinance_symbol` set), AND
        mutates the live override dicts in place so any holder of
        `coingecko_id_overrides()`/`yfinance_symbol_overrides()` observes the
        registration immediately (CRITICAL fix — see class docstring).
        """
        symbol = row.symbol.upper()
        self._rows[symbol] = row
        self._instruments[symbol] = _instrument_from_row(row)
        if row.coingecko_id:
            self._coingecko_overrides[row.symbol] = row.coingecko_id
        if row.yfinance_symbol:
            self._yfinance_overrides[row.symbol] = row.yfinance_symbol

    def coingecko_id_overrides(self) -> dict[str, str]:
        """Return the LIVE `symbol -> coingecko_id` override dict (not a copy).

        Callers (e.g. `Container.get_market_data_provider`) must hold onto this
        exact object rather than re-snapshotting it, so registrations made via
        `add_row()` after the provider was built are still visible.
        """
        return self._coingecko_overrides

    def yfinance_symbol_overrides(self) -> dict[str, str]:
        """Return the LIVE `symbol -> yfinance_symbol` override dict (not a copy)."""
        return self._yfinance_overrides


def _instrument_from_row(row: InstrumentRow) -> Instrument:
    """Map a raw catalog row onto the pure `Instrument` entity, dropping vendor ids."""
    return Instrument(
        symbol=row.symbol,
        name=row.name,
        asset_class=row.asset_class,
        currency=row.currency,
    )
