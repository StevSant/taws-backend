"""`ListEnrichedInstruments` degrades ONE dark instrument, never the whole page.

Regression cover for the markets-explorer blackout: `_enrich` awaited `ComputeMarketStats`
unguarded and `asyncio.gather` ran without `return_exceptions`, so a single instrument whose
price provider was unavailable (a rate-limited crypto symbol, say) raised
`MarketDataUnavailableError` out of `execute()`. The API middleware then mapped that to a 503
for the ENTIRE explorer — 27 perfectly healthy rows taken down by one dark symbol, despite the
class docstring promising per-row degradation.

The contract asserted here: a failing price fetch nulls that row's market metrics and empties
its sparkline (exactly what `EnrichedInstrumentResponse` documents its nullable fields to mean)
and every other row keeps its data.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.application.instruments.use_cases.list_enriched_instruments import (
    ListEnrichedInstruments,
)
from app.domain.market.entities import (
    AssetClass,
    Instrument,
    InstrumentMetadata,
    PriceCandle,
    PriceSeries,
)
from app.domain.market.errors import MarketDataUnavailableError
from app.domain.market.ports import (
    InstrumentMetadataProvider,
    InstrumentUniverse,
    MarketDataProvider,
)
from app.domain.signals.ports import SignalRepository

_EPOCH = datetime(2026, 7, 1, tzinfo=UTC)

_BTC = Instrument(symbol="BTC", name="Bitcoin", asset_class=AssetClass.CRYPTO, currency="USD")
_ETH = Instrument(symbol="ETH", name="Ethereum", asset_class=AssetClass.CRYPTO, currency="USD")
_AAPL = Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD")


class _FakeUniverse(InstrumentUniverse):
    def __init__(self, instruments: list[Instrument]) -> None:
        self._instruments = instruments

    def all(self) -> list[Instrument]:
        return list(self._instruments)

    def by_symbol(self, symbol: str) -> Instrument | None:
        for instrument in self._instruments:
            if instrument.symbol.upper() == symbol.upper():
                return instrument
        return None

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [i for i in self._instruments if i.asset_class == asset_class]


class _DarkForOneSymbolProvider(MarketDataProvider):
    """Serves real candles for everyone EXCEPT `dark_symbol`, which raises — the shape
    `RoutingMarketDataProvider` produces when its upstream returns no candles."""

    def __init__(self, dark_symbol: str) -> None:
        self._dark_symbol = dark_symbol

    async def get_price_series(self, instrument: Instrument, days: int = 30) -> PriceSeries:
        if instrument.symbol == self._dark_symbol:
            raise MarketDataUnavailableError(
                instrument.symbol, "upstream provider returned no candles"
            )
        return PriceSeries(
            symbol=instrument.symbol,
            candles=[
                PriceCandle(
                    timestamp=_EPOCH + timedelta(days=day),
                    open=10.0,
                    high=12.0,
                    low=9.0,
                    close=float(10 + day),
                )
                for day in range(5)
            ],
        )

    async def get_last_price(self, instrument: Instrument) -> float | None:
        if instrument.symbol == self._dark_symbol:
            raise MarketDataUnavailableError(instrument.symbol, "no price")
        return 14.0


class _EmptyMetadataProvider(InstrumentMetadataProvider):
    async def get_metadata_batch(self, symbols: list[str]) -> dict[str, InstrumentMetadata]:
        return {}


class _FakeSignalRepository(SignalRepository):
    async def create(self, signal):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def get(self, signal_id: str):  # type: ignore[no-untyped-def]
        return None

    async def get_by_ids(self, signal_ids):  # type: ignore[no-untyped-def]
        return {}

    async def list_for_instrument(self, symbol: str):  # type: ignore[no-untyped-def]
        return []

    async def save_review_state(self, review_state):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def list_review_states(self, signal_id: str):  # type: ignore[no-untyped-def]
        return []

    async def get_latest_for_instrument(self, symbol: str, locale: str):  # type: ignore[no-untyped-def]
        return None

    async def prune_for_instrument(self, symbol: str, locale: str, keep: int):  # type: ignore[no-untyped-def]
        return None


def _build_use_case(dark_symbol: str) -> ListEnrichedInstruments:
    return ListEnrichedInstruments(
        instrument_universe=_FakeUniverse([_BTC, _ETH, _AAPL]),
        market_data_provider=_DarkForOneSymbolProvider(dark_symbol),
        signal_repository=_FakeSignalRepository(),
        instrument_metadata_provider=_EmptyMetadataProvider(),
    )


async def test_one_dark_instrument_does_not_fail_the_whole_page() -> None:
    page = await _build_use_case(dark_symbol="BTC").execute(locale="es")

    # The bug: this used to raise MarketDataUnavailableError -> 503 for all three rows.
    assert {item.symbol for item in page.items} == {"BTC", "ETH", "AAPL"}


async def test_the_dark_instrument_row_degrades_to_null_metrics() -> None:
    page = await _build_use_case(dark_symbol="BTC").execute(locale="es")

    btc = next(item for item in page.items if item.symbol == "BTC")
    assert btc.last_price is None
    assert btc.price_delta_pct is None
    assert btc.volatility_pct is None
    assert btc.sparkline == []


async def test_the_healthy_instruments_keep_their_metrics() -> None:
    page = await _build_use_case(dark_symbol="BTC").execute(locale="es")

    for symbol in ("ETH", "AAPL"):
        item = next(row for row in page.items if row.symbol == symbol)
        assert item.last_price is not None, f"{symbol} lost its price to BTC's failure"
        assert item.sparkline, f"{symbol} lost its sparkline to BTC's failure"


@pytest.mark.parametrize("dark_symbol", ["BTC", "ETH", "AAPL"])
async def test_any_single_dark_instrument_still_yields_a_full_page(dark_symbol: str) -> None:
    page = await _build_use_case(dark_symbol).execute(locale="es")

    assert len(page.items) == 3
