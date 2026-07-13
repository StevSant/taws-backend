"""Track Instruments Catalog Slice 3 (enrichment): `GET /instruments/enriched` new fields.

Uses the `dependency_overrides` pattern from `test_quant_stats_candles.py`:
- Response includes `market_cap`, `volume_24h`, `change_7d_pct` per row, existing
  10 fields unchanged, when the metadata provider is a fake returning fixed values.
- A CoinGecko-down fake (returns `{}`) -> 200, every row present, the 3 new fields
  `null` on every row — no crash, no missing rows.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.v1.dependencies import (
    get_instrument_metadata_provider,
    get_instrument_universe,
    get_market_data_provider,
    get_signal_repository,
)
from app.domain.market.entities import AssetClass, Instrument, InstrumentMetadata, PriceSeries
from app.domain.market.ports import InstrumentMetadataProvider, MarketDataProvider
from app.domain.signals.ports import SignalRepository
from app.infrastructure.universe.supabase_instrument_universe import SupabaseInstrumentUniverse
from app.main import create_app

_BTC_ROW = Instrument(symbol="BTC", name="Bitcoin", asset_class=AssetClass.CRYPTO, currency="USD")
_AAPL_ROW = Instrument(
    symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"
)


class _FakeMarketDataProvider(MarketDataProvider):
    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        return PriceSeries(symbol=instrument.symbol, candles=[])

    async def get_last_price(self, instrument: Instrument) -> float | None:
        return None


class _FakeSignalRepository(SignalRepository):
    async def create(self, signal):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def get(self, signal_id: str):  # type: ignore[no-untyped-def]
        return None

    async def list_for_instrument(self, symbol: str):  # type: ignore[no-untyped-def]
        return []

    async def save_review_state(self, review_state):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def list_review_states(self, signal_id: str):  # type: ignore[no-untyped-def]
        return []


class _FixedMetadataProvider(InstrumentMetadataProvider):
    """Returns a fixed reading for BTC only; AAPL is absent (no CoinGecko mapping)."""

    async def get_metadata_batch(self, symbols: list[str]) -> dict[str, InstrumentMetadata]:
        if "BTC" not in symbols:
            return {}
        return {
            "BTC": InstrumentMetadata(
                market_cap=1_200_000_000_000.0, volume_24h=45_000_000_000.0, change_7d_pct=5.5
            )
        }


class _DownMetadataProvider(InstrumentMetadataProvider):
    """Simulates CoinGecko fully unavailable — always returns an empty dict."""

    async def get_metadata_batch(self, symbols: list[str]) -> dict[str, InstrumentMetadata]:
        return {}


def _build_client(metadata_provider: InstrumentMetadataProvider) -> TestClient:
    app = create_app()
    universe = SupabaseInstrumentUniverse([])
    universe.add(_BTC_ROW)
    universe.add(_AAPL_ROW)

    app.dependency_overrides[get_instrument_universe] = lambda: universe
    app.dependency_overrides[get_market_data_provider] = lambda: _FakeMarketDataProvider()
    app.dependency_overrides[get_signal_repository] = lambda: _FakeSignalRepository()
    app.dependency_overrides[get_instrument_metadata_provider] = lambda: metadata_provider
    return TestClient(app)


@pytest.fixture
def fixed_metadata_client() -> Iterator[TestClient]:
    client = _build_client(_FixedMetadataProvider())
    yield client
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


@pytest.fixture
def down_metadata_client() -> Iterator[TestClient]:
    client = _build_client(_DownMetadataProvider())
    yield client
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def test_response_includes_new_fields_and_existing_fields_unchanged(
    fixed_metadata_client: TestClient,
) -> None:
    response = fixed_metadata_client.get("/api/v1/instruments/enriched")

    assert response.status_code == 200
    items = response.json()["items"]
    by_symbol = {item["symbol"]: item for item in items}

    btc = by_symbol["BTC"]
    assert btc["market_cap"] == 1_200_000_000_000.0
    assert btc["volume_24h"] == 45_000_000_000.0
    assert btc["change_7d_pct"] == 5.5
    # Existing 10 fields still present/unchanged in shape.
    assert btc["name"] == "Bitcoin"
    assert btc["asset_class"] == "crypto"
    assert btc["currency"] == "USD"
    assert "last_price" in btc
    assert "price_delta_pct" in btc
    assert "volatility_pct" in btc
    assert "volatility_regime" in btc
    assert "sparkline" in btc
    assert "latest_signal" in btc

    aapl = by_symbol["AAPL"]
    assert aapl["market_cap"] is None
    assert aapl["volume_24h"] is None
    assert aapl["change_7d_pct"] is None


def test_coingecko_fully_down_returns_200_all_rows_present_all_null(
    down_metadata_client: TestClient,
) -> None:
    response = down_metadata_client.get("/api/v1/instruments/enriched")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    for item in items:
        assert item["market_cap"] is None
        assert item["volume_24h"] is None
        assert item["change_7d_pct"] is None
