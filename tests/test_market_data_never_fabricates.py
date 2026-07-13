"""Regression guard for the "$333.6 BTC" incident: the price path must never fabricate data.

A keyless CoinGecko 429 tripped the adapter's circuit breaker, which returned an empty
series; `RoutingMarketDataProvider` then silently substituted a sha256-seeded random walk
priced in a $20-$500 band. BTC was charted at $333.6 (-11.15% over a year) while it really
traded near $63,000, the chart was labelled "market data", and the LLM faithfully repeated
the fabricated number to the user — then reasoned an investment recommendation on top of it.

The contract these tests pin down: when live market data is unavailable, the provider
RAISES `MarketDataUnavailableError`, and every agent tool tells the model the data is
unavailable instead of handing it a number. Synthetic prices must not exist in production
code at all.
"""

from pathlib import Path

import pytest

from app.application.charts.use_cases import BuildPriceChart
from app.application.quant.use_cases.compute_market_stats import ComputeMarketStats
from app.domain.charts.entities import ChartConfig
from app.domain.market.entities import AssetClass, Instrument, PriceSeries
from app.domain.market.errors import MarketDataUnavailableError
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider
from app.infrastructure.agents.tools.get_market_stats_tool import build_get_market_stats_tool
from app.infrastructure.agents.tools.render_price_chart_tool import build_render_price_chart_tool
from app.infrastructure.marketdata import RoutingMarketDataProvider

_BTC = Instrument(symbol="BTC", name="Bitcoin", asset_class=AssetClass.CRYPTO, currency="USD")

_CHART_CONFIG = ChartConfig(
    default_timeframe="1y",
    max_points=200,
    available_timeframes=["1m", "1y"],
    timeframe_days={"1m": 30, "1y": 365},
)


class _StubUniverse(InstrumentUniverse):
    def all(self) -> list[Instrument]:
        return [_BTC]

    def by_symbol(self, symbol: str) -> Instrument | None:
        return _BTC if symbol.upper() == "BTC" else None

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [_BTC] if asset_class == AssetClass.CRYPTO else []


class _ExplodingProvider(MarketDataProvider):
    """A live adapter that is down — the CoinGecko-429 case."""

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        raise RuntimeError("429 Too Many Requests")

    async def get_last_price(self, instrument: Instrument) -> float | None:
        raise RuntimeError("429 Too Many Requests")


class _EmptyProvider(MarketDataProvider):
    """A live adapter that returns nothing — what the CoinGecko circuit breaker does."""

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        return PriceSeries(symbol=instrument.symbol, candles=[])

    async def get_last_price(self, instrument: Instrument) -> float | None:
        return None


def _routing(primary: MarketDataProvider) -> RoutingMarketDataProvider:
    return RoutingMarketDataProvider(yfinance_provider=primary, coingecko_provider=primary)


@pytest.mark.parametrize("primary", [_ExplodingProvider(), _EmptyProvider()])
async def test_price_series_raises_instead_of_fabricating(primary: MarketDataProvider) -> None:
    with pytest.raises(MarketDataUnavailableError):
        await _routing(primary).get_price_series(_BTC, days=365)


@pytest.mark.parametrize("primary", [_ExplodingProvider(), _EmptyProvider()])
async def test_last_price_raises_instead_of_fabricating(primary: MarketDataProvider) -> None:
    with pytest.raises(MarketDataUnavailableError):
        await _routing(primary).get_last_price(_BTC)


def test_no_synthetic_market_data_provider_ships_in_production_code() -> None:
    """The fixture generator must not exist under `src/` — not even unwired.

    A dormant `FixtureMarketDataProvider` is one DI line away from being served as real
    prices again. Deterministic test doubles belong in `tests/`.
    """
    src = Path(__file__).resolve().parents[1] / "src"
    offenders = [
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if "fixture" in path.name and "market_data" in path.name
    ]
    assert offenders == [], f"synthetic market-data providers still in production code: {offenders}"


async def test_market_stats_tool_reports_unavailable_rather_than_a_number() -> None:
    tool = build_get_market_stats_tool(
        ComputeMarketStats(
            market_data_provider=_routing(_ExplodingProvider()),
            instrument_universe=_StubUniverse(),
        )
    )

    result = await tool.coroutine(instrument_symbol="BTC", window_days=365)

    assert "unavailable" in result.lower()
    assert "333" not in result


async def test_price_chart_tool_reports_unavailable_and_emits_no_chart() -> None:
    """No chart may be pushed to the user when the data behind it doesn't exist.

    The tool returns before reaching `get_stream_writer()`, so this also asserts (by not
    blowing up outside a LangGraph runtime) that no chart event is emitted.
    """
    tool = build_render_price_chart_tool(
        BuildPriceChart(
            market_data_provider=_routing(_ExplodingProvider()),
            instrument_universe=_StubUniverse(),
            chart_config=_CHART_CONFIG,
        ),
        _CHART_CONFIG,
    )

    result = await tool.coroutine(instrument_symbol="BTC", timeframe="1y")

    assert "unavailable" in result.lower()
    assert "333" not in result
