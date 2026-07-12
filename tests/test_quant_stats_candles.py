"""Track 5 criterion 2b: `GET /api/v1/quant/stats` exposes an OHLC candle series.

Verifies the additive `candles` field on the market-stats response: exact keys
(t,o,h,l,c,v), oldest -> newest order, and an empty list (never null) when the
instrument has no price series. Uses `FixtureMarketDataProvider` for determinism.
"""

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_instrument_universe, get_market_data_provider
from app.domain.market.entities import AssetClass, Instrument, PriceSeries
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider
from app.infrastructure.marketdata import FixtureMarketDataProvider
from app.main import create_app

_KNOWN_SYMBOL = "AAPL"

_KNOWN_INSTRUMENT = Instrument(
    symbol=_KNOWN_SYMBOL,
    name="Apple Inc.",
    asset_class=AssetClass.STOCK,
    currency="USD",
)


class _StubInstrumentUniverse(InstrumentUniverse):
    """Resolves only `_KNOWN_SYMBOL`, so the endpoint has a deterministic instrument."""

    def all(self) -> list[Instrument]:
        return [_KNOWN_INSTRUMENT]

    def by_symbol(self, symbol: str) -> Instrument | None:
        return _KNOWN_INSTRUMENT if symbol.upper() == _KNOWN_SYMBOL else None

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [_KNOWN_INSTRUMENT] if asset_class == AssetClass.STOCK else []


class _EmptyMarketDataProvider(MarketDataProvider):
    """Always returns an empty price series — the 'no series available' branch."""

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        return PriceSeries(symbol=instrument.symbol, candles=[])

    async def get_last_price(self, instrument: Instrument) -> float | None:
        return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_instrument_universe] = lambda: _StubInstrumentUniverse()
    app.dependency_overrides[get_market_data_provider] = FixtureMarketDataProvider
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_stats_response_includes_candles_with_exact_keys_oldest_to_newest(
    client: TestClient,
) -> None:
    response = client.get(f"/api/v1/quant/stats?instrument={_KNOWN_SYMBOL}&window_days=10")

    assert response.status_code == 200
    body = response.json()

    assert "candles" in body
    candles = body["candles"]
    assert isinstance(candles, list)
    assert len(candles) == 10

    for candle in candles:
        assert set(candle.keys()) == {"t", "o", "h", "l", "c", "v"}
        assert isinstance(candle["o"], float)
        assert isinstance(candle["h"], float)
        assert isinstance(candle["l"], float)
        assert isinstance(candle["c"], float)

    timestamps = [datetime.fromisoformat(candle["t"]) for candle in candles]
    assert timestamps == sorted(timestamps), "candles must be ordered oldest -> newest"


def test_stats_response_keeps_existing_fields_backward_compatible(client: TestClient) -> None:
    response = client.get(f"/api/v1/quant/stats?instrument={_KNOWN_SYMBOL}&window_days=10")

    assert response.status_code == 200
    body = response.json()

    for field in (
        "instrument_symbol",
        "window_days",
        "last_price",
        "price_delta_pct",
        "volatility_pct",
        "volatility_regime",
        "unusual_moves",
        "as_of",
    ):
        assert field in body


def test_stats_response_candles_is_empty_list_when_no_series() -> None:
    app = create_app()
    app.dependency_overrides[get_instrument_universe] = lambda: _StubInstrumentUniverse()
    app.dependency_overrides[get_market_data_provider] = _EmptyMarketDataProvider
    client = TestClient(app)
    try:
        response = client.get(f"/api/v1/quant/stats?instrument={_KNOWN_SYMBOL}&window_days=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["candles"] == []
