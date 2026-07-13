"""Track Instruments Catalog Slice 3 (enrichment): `ListEnrichedInstruments` metadata merge.

`ListEnrichedInstruments` is now injected with an `InstrumentMetadataProvider` and
does ONE batch call for all symbols in the page — never one call per instrument.
Merges `market_cap`/`volume_24h`/`change_7d_pct` per row when present; a symbol
absent from the batch result (or the whole provider failing/returning `{}`) still
produces a fully present row with all three new fields `None` — no crash, no
missing rows (instrument-enrichment spec's "degrade gracefully").
"""

from app.application.instruments.use_cases.list_enriched_instruments import (
    ListEnrichedInstruments,
)
from app.domain.market.entities import AssetClass, Instrument, InstrumentMetadata, PriceSeries
from app.domain.market.ports import (
    InstrumentMetadataProvider,
    InstrumentUniverse,
    MarketDataProvider,
)
from app.domain.signals.ports import SignalRepository

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

    async def get_latest_for_instrument(self, symbol: str, locale: str):  # type: ignore[no-untyped-def]
        return None

    async def prune_for_instrument(self, symbol: str, locale: str, keep: int):  # type: ignore[no-untyped-def]
        return None


class _FakeMetadataProvider(InstrumentMetadataProvider):
    """Records every `symbols` argument passed, to assert a single batch call."""

    def __init__(self, metadata_by_symbol: dict[str, InstrumentMetadata]) -> None:
        self._metadata_by_symbol = metadata_by_symbol
        self.calls: list[list[str]] = []

    async def get_metadata_batch(self, symbols: list[str]) -> dict[str, InstrumentMetadata]:
        self.calls.append(list(symbols))
        return {
            symbol: metadata
            for symbol, metadata in self._metadata_by_symbol.items()
            if symbol in symbols
        }


class _AlwaysEmptyMetadataProvider(InstrumentMetadataProvider):
    async def get_metadata_batch(self, symbols: list[str]) -> dict[str, InstrumentMetadata]:
        return {}


def _build_use_case(
    instruments: list[Instrument], metadata_provider: InstrumentMetadataProvider
) -> ListEnrichedInstruments:
    return ListEnrichedInstruments(
        instrument_universe=_FakeUniverse(instruments),
        market_data_provider=_FakeMarketDataProvider(),
        signal_repository=_FakeSignalRepository(),
        instrument_metadata_provider=metadata_provider,
    )


async def test_does_one_batch_call_for_all_symbols_in_the_page() -> None:
    metadata_provider = _FakeMetadataProvider(
        {
            "BTC": InstrumentMetadata(market_cap=1.0, volume_24h=2.0, change_7d_pct=3.0),
            "ETH": InstrumentMetadata(market_cap=4.0, volume_24h=5.0, change_7d_pct=6.0),
        }
    )
    use_case = _build_use_case([_BTC, _ETH], metadata_provider)

    await use_case.execute(locale="es")

    assert len(metadata_provider.calls) == 1
    assert set(metadata_provider.calls[0]) == {"BTC", "ETH"}


async def test_merges_metadata_per_row_when_present() -> None:
    metadata_provider = _FakeMetadataProvider(
        {
            "BTC": InstrumentMetadata(market_cap=1.0, volume_24h=2.0, change_7d_pct=3.0),
            "ETH": InstrumentMetadata(market_cap=4.0, volume_24h=5.0, change_7d_pct=6.0),
        }
    )
    use_case = _build_use_case([_BTC, _ETH], metadata_provider)

    page = await use_case.execute(locale="es")

    by_symbol = {item.symbol: item for item in page.items}
    assert by_symbol["BTC"].market_cap == 1.0
    assert by_symbol["BTC"].volume_24h == 2.0
    assert by_symbol["BTC"].change_7d_pct == 3.0
    assert by_symbol["ETH"].market_cap == 4.0
    assert by_symbol["ETH"].volume_24h == 5.0
    assert by_symbol["ETH"].change_7d_pct == 6.0


async def test_symbol_absent_from_batch_result_gets_null_fields_row_still_present() -> None:
    metadata_provider = _FakeMetadataProvider(
        {"BTC": InstrumentMetadata(market_cap=1.0, volume_24h=2.0, change_7d_pct=3.0)}
    )
    use_case = _build_use_case([_BTC, _AAPL], metadata_provider)

    page = await use_case.execute(locale="es")

    assert len(page.items) == 2
    by_symbol = {item.symbol: item for item in page.items}
    assert by_symbol["AAPL"].market_cap is None
    assert by_symbol["AAPL"].volume_24h is None
    assert by_symbol["AAPL"].change_7d_pct is None


async def test_provider_returning_empty_dict_leaves_all_rows_present_with_null_fields() -> None:
    use_case = _build_use_case([_BTC, _ETH, _AAPL], _AlwaysEmptyMetadataProvider())

    page = await use_case.execute(locale="es")

    assert len(page.items) == 3
    for item in page.items:
        assert item.market_cap is None
        assert item.volume_24h is None
        assert item.change_7d_pct is None
