"""Track Instruments Catalog Slice 2 router wiring:

- `GET /api/v1/instruments/search?q=` delegates to `SearchCoins` (ranked candidates,
  empty list on no hits) — instrument-search spec.
- `POST /api/v1/instruments` delegates to `RegisterInstrument` (authenticated):
  201 success (visible in a subsequent `GET /instruments`, SC2), 201 no-dup on
  re-registration (SC4), 409 on symbol collision with an existing non-crypto row
  (stock row unchanged), 502 when the catalog/universe writes succeed but the
  watchlist add fails (persisted instrument + `watchlisted: false` in the body).

Uses the `dependency_overrides` pattern from `test_quant_stats_candles.py`.
"""

from collections.abc import Iterator, Sequence

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import (
    get_coingecko_search_provider,
    get_instrument_universe,
    get_register_instrument_use_case,
    get_search_coins_use_case,
    get_watchlist_repository,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser
from app.application.instruments.use_cases import RegisterInstrument, SearchCoins
from app.domain.market.entities import AssetClass, CoinCandidate, InstrumentRow
from app.domain.market.ports import CoinGeckoSearchProvider
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository
from app.infrastructure.universe.supabase_instrument_universe import SupabaseInstrumentUniverse
from app.main import create_app

_USER = CurrentUser(id="user-1", email="user@example.com")

_DOGE_CANDIDATE = CoinCandidate(
    id="dogecoin", symbol="doge", name="Dogecoin", market_cap_rank=10, thumb="doge.png"
)

_EXISTING_ROWS = [
    InstrumentRow(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"),
    InstrumentRow(
        symbol="COIN", name="Coinbase Global Inc.", asset_class=AssetClass.STOCK, currency="USD"
    ),
    InstrumentRow(
        symbol="BTC",
        name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
        coingecko_id="bitcoin",
    ),
]


class _FakeSearchProvider(CoinGeckoSearchProvider):
    """Returns a fixed candidate for `"doge"`, empty list for anything else."""

    async def search(self, query: str) -> list[CoinCandidate]:
        return [_DOGE_CANDIDATE] if query == "doge" else []


class _FakeWatchlistRepository(WatchlistRepository):
    """In-memory watchlist store; `fail_add` forces `add_item` to raise (502 path)."""

    def __init__(self, fail_add: bool = False) -> None:
        self._fail_add = fail_add
        self._watchlists: dict[str, Watchlist] = {}
        self._items: dict[str, list[WatchlistItem]] = {}
        self._next_item_id = 0

    async def create(self, watchlist: Watchlist) -> Watchlist:
        self._watchlists[watchlist.id] = watchlist
        self._items[watchlist.id] = []
        return watchlist

    async def get(self, watchlist_id: str) -> Watchlist | None:
        return self._watchlists.get(watchlist_id)

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        return [w for w in self._watchlists.values() if w.user_id == user_id]

    async def list_all(self) -> list[Watchlist]:
        return list(self._watchlists.values())

    async def list_user_ids_tracking(self, symbols: Sequence[str]) -> set[str]:
        raise NotImplementedError

    async def list_trackers_by_symbol(self, symbols: Sequence[str]) -> dict[str, set[str]]:
        return {}

    async def list_all_tracked_symbols(self) -> set[str]:
        return {
            item.symbol.strip().upper()
            for items in self._items.values()
            for item in items
            if item.symbol.strip()
        }

    async def rename(self, watchlist_id: str, name: str) -> Watchlist:
        raise NotImplementedError

    async def delete(self, watchlist_id: str) -> None:
        raise NotImplementedError

    async def list_items(self, watchlist_id: str) -> list[WatchlistItem]:
        return list(self._items.get(watchlist_id, []))

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        if self._fail_add:
            raise RuntimeError("watchlist store unavailable")
        existing = [item for item in self._items[watchlist_id] if item.symbol == symbol]
        if existing:
            return existing[0]
        self._next_item_id += 1
        item = WatchlistItem(
            id=f"item-{self._next_item_id}", watchlist_id=watchlist_id, symbol=symbol
        )
        self._items[watchlist_id].append(item)
        return item

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        raise NotImplementedError

    async def reorder(self, user_id: str, ordered_ids: list[str]) -> None:
        raise NotImplementedError


def _make_client(
    universe: SupabaseInstrumentUniverse,
    watchlist_repository: WatchlistRepository,
    search_provider: CoinGeckoSearchProvider | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_instrument_universe] = lambda: universe
    app.dependency_overrides[require_current_user] = lambda: _USER
    app.dependency_overrides[get_coingecko_search_provider] = lambda: (
        search_provider or _FakeSearchProvider()
    )
    app.dependency_overrides[get_search_coins_use_case] = lambda: SearchCoins(
        search_provider=search_provider or _FakeSearchProvider()
    )
    app.dependency_overrides[get_register_instrument_use_case] = lambda: RegisterInstrument(
        catalog_repository=_NoopCatalogRepository(),
        universe=universe,
        watchlist_repository=watchlist_repository,
    )
    app.dependency_overrides[get_watchlist_repository] = lambda: watchlist_repository
    return TestClient(app)


class _NoopCatalogRepository:
    """The router test only cares about universe/watchlist side-effects; the real
    Supabase catalog write is exercised by `test_register_instrument_use_case.py`
    and `test_supabase_instrument_catalog_repository.py`.
    """

    async def upsert(self, row: InstrumentRow) -> None:
        return None

    async def all_rows(self) -> list[InstrumentRow]:
        return []


@pytest.fixture
def universe() -> SupabaseInstrumentUniverse:
    return SupabaseInstrumentUniverse(list(_EXISTING_ROWS))


@pytest.fixture
def watchlist_repository() -> _FakeWatchlistRepository:
    return _FakeWatchlistRepository()


@pytest.fixture
def client(
    universe: SupabaseInstrumentUniverse, watchlist_repository: _FakeWatchlistRepository
) -> Iterator[TestClient]:
    test_client = _make_client(universe, watchlist_repository)
    yield test_client
    test_client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def test_search_returns_ranked_candidates_for_a_known_query(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/search?q=doge")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "id": "dogecoin",
            "symbol": "doge",
            "name": "Dogecoin",
            "market_cap_rank": 10,
            "thumb": "doge.png",
        }
    ]


def test_search_returns_empty_list_for_no_hits(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/search?q=zzz")

    assert response.status_code == 200
    assert response.json() == []


def test_register_new_coin_returns_201_and_is_visible_in_list_instruments(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/instruments",
        json={"coingecko_id": "dogecoin", "symbol": "doge", "name": "Dogecoin"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["watchlisted"] is True
    assert body["instrument"]["symbol"] == "DOGE"
    assert body["instrument"]["asset_class"] == "crypto"

    list_response = client.get("/api/v1/instruments")
    assert list_response.status_code == 200
    symbols = {item["symbol"] for item in list_response.json()}
    assert "DOGE" in symbols


def test_duplicate_register_returns_201_with_no_duplicate_row(
    client: TestClient, universe: SupabaseInstrumentUniverse
) -> None:
    payload = {"coingecko_id": "dogecoin", "symbol": "doge", "name": "Dogecoin"}

    first = client.post("/api/v1/instruments", json=payload)
    second = client.post("/api/v1/instruments", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201

    matches = [instrument for instrument in universe.all() if instrument.symbol == "DOGE"]
    assert len(matches) == 1


def test_register_existing_stock_symbol_returns_409_and_leaves_stock_row_unchanged(
    client: TestClient, universe: SupabaseInstrumentUniverse
) -> None:
    response = client.post(
        "/api/v1/instruments",
        json={"coingecko_id": "some-coin-token", "symbol": "COIN", "name": "Some Coin Token"},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["instrument"]["symbol"] == "COIN"
    assert body["detail"]["instrument"]["asset_class"] == "stock"

    stock_row = universe.by_symbol("COIN")
    assert stock_row is not None
    assert stock_row.name == "Coinbase Global Inc."
    assert stock_row.asset_class == AssetClass.STOCK


def test_register_rejects_malformed_symbol_with_422(client: TestClient) -> None:
    """MEDIUM fix (post-hoc adversarial review): schema-level bounds on `symbol`/
    `coingecko_id` reject junk before it ever reaches the service-role write."""
    response = client.post(
        "/api/v1/instruments",
        json={"coingecko_id": "dogecoin", "symbol": "<script>", "name": "Dogecoin"},
    )

    assert response.status_code == 422


def test_register_rejects_malformed_coingecko_id_with_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/instruments",
        json={"coingecko_id": "<script>alert(1)</script>", "symbol": "doge", "name": "Dogecoin"},
    )

    assert response.status_code == 422


def test_register_returns_502_when_watchlist_add_fails_after_catalog_persisted(
    universe: SupabaseInstrumentUniverse,
) -> None:
    failing_watchlist_repository = _FakeWatchlistRepository(fail_add=True)
    client = _make_client(universe, failing_watchlist_repository)
    try:
        response = client.post(
            "/api/v1/instruments",
            json={"coingecko_id": "dogecoin", "symbol": "doge", "name": "Dogecoin"},
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["watchlisted"] is False
    assert body["detail"]["instrument"]["symbol"] == "DOGE"

    persisted = universe.by_symbol("DOGE")
    assert persisted is not None
    assert persisted.asset_class == AssetClass.CRYPTO
