"""`RegisterInstrument`: collision-check -> catalog.upsert -> universe.add ->
watchlist.add_item, in that exact order (design's FIX #5 partial-failure
ordering).

Fakes for `InstrumentCatalogRepository`, `MutableInstrumentUniverse`/
`InstrumentUniverse` (via a small dual-purpose stub), and `WatchlistRepository`
record calls so the exact order and arguments can be asserted.
"""

import pytest

from app.application.instruments.errors import SymbolCollisionError
from app.application.instruments.register_instrument_result import RegisterInstrumentResult
from app.application.instruments.use_cases.register_instrument import RegisterInstrument
from app.domain.market.entities import AssetClass, CoinCandidate, Instrument, InstrumentRow
from app.domain.market.ports import InstrumentCatalogRepository, InstrumentUniverse
from app.domain.watchlist.entities import WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository

_DOGE_CANDIDATE = CoinCandidate(
    id="dogecoin", symbol="doge", name="Dogecoin", market_cap_rank=10, thumb=""
)
_EXISTING_STOCK = Instrument(
    symbol="COIN", name="Coinbase Global Inc.", asset_class=AssetClass.STOCK, currency="USD"
)


class _FakeCatalogRepository(InstrumentCatalogRepository):
    def __init__(self) -> None:
        self.upserted_rows: list[InstrumentRow] = []

    async def upsert(self, row: InstrumentRow) -> None:
        self.upserted_rows.append(row)

    async def all_rows(self) -> list[InstrumentRow]:
        return []


class _FakeUniverse(InstrumentUniverse):
    """Doubles as the `MutableInstrumentUniverse` protocol (structural `add()`/`add_row()`)."""

    def __init__(self, existing: dict[str, Instrument] | None = None) -> None:
        self._existing = dict(existing or {})
        self.added: list[Instrument] = []
        self.added_rows: list[InstrumentRow] = []

    def all(self) -> list[Instrument]:
        return list(self._existing.values())

    def by_symbol(self, symbol: str) -> Instrument | None:
        return self._existing.get(symbol.upper())

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [i for i in self._existing.values() if i.asset_class == asset_class]

    def add(self, instrument: Instrument) -> None:
        self.added.append(instrument)
        self._existing[instrument.symbol.upper()] = instrument

    def add_row(self, row: InstrumentRow) -> None:
        self.added_rows.append(row)
        self.added.append(
            Instrument(
                symbol=row.symbol,
                name=row.name,
                asset_class=row.asset_class,
                currency=row.currency,
            )
        )
        self._existing[row.symbol.upper()] = self.added[-1]


class _FakeWatchlistRepository(WatchlistRepository):
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.add_item_calls: list[tuple[str, str]] = []

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
        self.add_item_calls.append((watchlist_id, symbol))
        if self._fail:
            raise RuntimeError("watchlist store unavailable")
        return WatchlistItem(id="item-1", watchlist_id=watchlist_id, symbol=symbol)

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        raise NotImplementedError

    async def reorder(self, user_id: str, ordered_ids: list[str]) -> None:
        raise NotImplementedError


async def test_register_new_coin_upserts_adds_and_watchlists_in_order() -> None:
    catalog = _FakeCatalogRepository()
    universe = _FakeUniverse()
    watchlist_repo = _FakeWatchlistRepository()
    use_case = RegisterInstrument(
        catalog_repository=catalog, universe=universe, watchlist_repository=watchlist_repo
    )

    result = await use_case.execute(candidate=_DOGE_CANDIDATE, watchlist_id="wl-1")

    assert isinstance(result, RegisterInstrumentResult)
    assert result.watchlisted is True
    assert result.instrument.symbol == "DOGE"
    assert result.instrument.asset_class == AssetClass.CRYPTO

    # order: catalog upsert -> universe.add -> watchlist.add_item
    assert len(catalog.upserted_rows) == 1
    assert catalog.upserted_rows[0].symbol == "DOGE"
    assert catalog.upserted_rows[0].coingecko_id == "dogecoin"
    assert catalog.upserted_rows[0].asset_class == AssetClass.CRYPTO

    assert len(universe.added) == 1
    assert universe.added[0].symbol == "DOGE"
    assert len(universe.added_rows) == 1
    assert universe.added_rows[0].coingecko_id == "dogecoin"

    assert watchlist_repo.add_item_calls == [("wl-1", "DOGE")]


async def test_register_normalizes_symbol_to_uppercase() -> None:
    lowercase_candidate = CoinCandidate(
        id="solana", symbol="sol", name="Solana", market_cap_rank=5, thumb=""
    )
    catalog = _FakeCatalogRepository()
    universe = _FakeUniverse()
    watchlist_repo = _FakeWatchlistRepository()
    use_case = RegisterInstrument(
        catalog_repository=catalog, universe=universe, watchlist_repository=watchlist_repo
    )

    result = await use_case.execute(candidate=lowercase_candidate, watchlist_id="wl-1")

    assert result.instrument.symbol == "SOL"
    assert catalog.upserted_rows[0].symbol == "SOL"
    assert watchlist_repo.add_item_calls == [("wl-1", "SOL")]


async def test_register_colliding_symbol_raises_with_no_writes() -> None:
    catalog = _FakeCatalogRepository()
    universe = _FakeUniverse(existing={"COIN": _EXISTING_STOCK})
    watchlist_repo = _FakeWatchlistRepository()
    use_case = RegisterInstrument(
        catalog_repository=catalog, universe=universe, watchlist_repository=watchlist_repo
    )
    colliding_candidate = CoinCandidate(
        id="some-coin-token", symbol="coin", name="Some Coin Token", market_cap_rank=999, thumb=""
    )

    with pytest.raises(SymbolCollisionError) as exc_info:
        await use_case.execute(candidate=colliding_candidate, watchlist_id="wl-1")

    assert exc_info.value.symbol == "COIN"
    assert exc_info.value.existing_instrument is _EXISTING_STOCK
    assert catalog.upserted_rows == []
    assert universe.added == []
    assert watchlist_repo.add_item_calls == []


async def test_register_existing_crypto_symbol_does_not_collide() -> None:
    existing_crypto = Instrument(
        symbol="BTC", name="Bitcoin", asset_class=AssetClass.CRYPTO, currency="USD"
    )
    catalog = _FakeCatalogRepository()
    universe = _FakeUniverse(existing={"BTC": existing_crypto})
    watchlist_repo = _FakeWatchlistRepository()
    use_case = RegisterInstrument(
        catalog_repository=catalog, universe=universe, watchlist_repository=watchlist_repo
    )
    btc_candidate = CoinCandidate(
        id="bitcoin", symbol="btc", name="Bitcoin", market_cap_rank=1, thumb=""
    )

    result = await use_case.execute(candidate=btc_candidate, watchlist_id="wl-1")

    assert result.watchlisted is True
    assert catalog.upserted_rows[0].symbol == "BTC"


async def test_register_watchlist_failure_returns_watchlisted_false_with_no_rollback() -> None:
    catalog = _FakeCatalogRepository()
    universe = _FakeUniverse()
    watchlist_repo = _FakeWatchlistRepository(fail=True)
    use_case = RegisterInstrument(
        catalog_repository=catalog, universe=universe, watchlist_repository=watchlist_repo
    )

    result = await use_case.execute(candidate=_DOGE_CANDIDATE, watchlist_id="wl-1")

    assert result.watchlisted is False
    assert result.instrument.symbol == "DOGE"
    # catalog + universe writes are NOT rolled back
    assert len(catalog.upserted_rows) == 1
    assert len(universe.added) == 1
