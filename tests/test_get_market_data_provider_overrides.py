"""`Container.get_market_data_provider()`'s vendor-id override sourcing (FIX #7).

Overrides now come from the prebuilt `SupabaseInstrumentUniverse.all_rows()`, not
`load_universe_seed(...)` — `RoutingMarketDataProvider` must still receive the exact
same override maps either way (instrument-catalog spec: "vendor overrides still
reach RoutingMarketDataProvider").
"""

from app.core.config import Settings
from app.core.di import Container
from app.domain.market.entities import InstrumentRow
from app.domain.market.entities.asset_class import AssetClass
from app.domain.market.ports import InstrumentCatalogRepository
from app.infrastructure.marketdata import RoutingMarketDataProvider


class _FakeInstrumentCatalogRepository(InstrumentCatalogRepository):
    def __init__(self, rows: list[InstrumentRow]) -> None:
        self._rows = rows

    async def upsert(self, row: InstrumentRow) -> None:
        self._rows.append(row)

    async def all_rows(self) -> list[InstrumentRow]:
        return list(self._rows)


_FIXTURE_ROWS = [
    InstrumentRow(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"),
    InstrumentRow(
        symbol="BTC",
        name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
        coingecko_id="bitcoin",
    ),
    InstrumentRow(
        symbol="EURUSD",
        name="Euro / US Dollar",
        asset_class=AssetClass.FOREX,
        currency="USD",
        yfinance_symbol="EURUSD=X",
    ),
]


async def test_market_data_provider_reads_overrides_from_universe_all_rows() -> None:
    container = Container(settings=Settings())
    container.get_instrument_catalog_repository = lambda: _FakeInstrumentCatalogRepository(  # type: ignore[method-assign]
        list(_FIXTURE_ROWS)
    )
    await container.build_instrument_universe()

    provider = container.get_market_data_provider()

    assert isinstance(provider, RoutingMarketDataProvider)
    assert provider._coingecko_provider._overrides == {"BTC": "bitcoin"}
    assert provider._yfinance_provider._symbol_overrides == {"EURUSD": "EURUSD=X"}
