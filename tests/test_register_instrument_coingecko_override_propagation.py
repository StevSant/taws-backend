"""CRITICAL regression: `RegisterInstrument.execute` must append the newly
registered coin to the universe via `add_row()` (not `add()`), so its
`coingecko_id` reaches the shared override dict the price provider holds a
live reference to. `add(instrument)` alone rebuilds a vendor-id-less
`InstrumentRow`, silently dropping the id until process restart.
"""

from app.application.instruments.use_cases.register_instrument import RegisterInstrument
from app.domain.market.entities import AssetClass, CoinCandidate, Instrument, InstrumentRow
from app.domain.market.ports import InstrumentCatalogRepository
from app.domain.watchlist.entities import WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.universe.supabase_instrument_universe import SupabaseInstrumentUniverse

_DOGE_CANDIDATE = CoinCandidate(
    id="dogecoin", symbol="doge", name="Dogecoin", market_cap_rank=10, thumb=""
)


class _FakeCatalogRepository(InstrumentCatalogRepository):
    def __init__(self, rows: list[InstrumentRow]) -> None:
        self._rows = list(rows)

    async def upsert(self, row: InstrumentRow) -> None:
        self._rows = [r for r in self._rows if r.symbol != row.symbol] + [row]

    async def all_rows(self) -> list[InstrumentRow]:
        return list(self._rows)


class _FakeWatchlistRepository(WatchlistRepository):
    async def create(self, watchlist):  # noqa: ANN001
        raise NotImplementedError

    async def get(self, watchlist_id: str):  # noqa: ANN001
        raise NotImplementedError

    async def list_for_user(self, user_id: str):  # noqa: ANN001
        raise NotImplementedError

    async def list_all(self):  # noqa: ANN001
        raise NotImplementedError

    async def rename(self, watchlist_id: str, name: str):  # noqa: ANN001
        raise NotImplementedError

    async def delete(self, watchlist_id: str) -> None:
        raise NotImplementedError

    async def list_items(self, watchlist_id: str):  # noqa: ANN001
        raise NotImplementedError

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        return WatchlistItem(id="item-1", watchlist_id=watchlist_id, symbol=symbol)

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        raise NotImplementedError


_SEED_ROW = InstrumentRow(
    symbol="BTC",
    name="Bitcoin",
    asset_class=AssetClass.CRYPTO,
    currency="USD",
    coingecko_id="bitcoin",
)


async def test_register_instrument_makes_new_coin_resolvable_via_live_overrides() -> None:
    """After registering a new coin, the universe's `coingecko_id_overrides()`
    map (the SAME dict object a cached `CoinGeckoMarketDataProvider` would hold)
    must contain its `coingecko_id` — proving the price provider can resolve it
    without a container/process restart."""
    catalog = _FakeCatalogRepository([_SEED_ROW])
    universe = await SupabaseInstrumentUniverse.create(catalog)
    watchlist_repo = _FakeWatchlistRepository()
    use_case = RegisterInstrument(
        catalog_repository=catalog, universe=universe, watchlist_repository=watchlist_repo
    )
    # Simulate a provider that captured the live override dict reference at
    # container build time, BEFORE this registration happens.
    live_overrides_ref = universe.coingecko_id_overrides()
    assert "DOGE" not in live_overrides_ref

    result = await use_case.execute(candidate=_DOGE_CANDIDATE, watchlist_id="wl-1")

    assert result.instrument.symbol == "DOGE"
    assert live_overrides_ref["DOGE"] == "dogecoin"
    assert universe.coingecko_id_overrides()["DOGE"] == "dogecoin"
    all_rows = universe.all_rows()
    doge_row = next(row for row in all_rows if row.symbol == "DOGE")
    assert doge_row.coingecko_id == "dogecoin"
    # Sanity: rebuilding an Instrument from the fake registry never leaks vendor ids.
    assert isinstance(result.instrument, Instrument)
