import asyncio
import logging

from app.application.instruments.enriched_instrument import EnrichedInstrument
from app.application.instruments.instrument_highlights import InstrumentHighlights
from app.application.instruments.instrument_page import InstrumentPage
from app.application.instruments.instrument_sort_field import InstrumentSortField
from app.application.instruments.sort_direction import SortDirection
from app.application.quant.use_cases import ComputeMarketStats
from app.domain.market.entities import AssetClass, Instrument, InstrumentMetadata, PriceCandle
from app.domain.market.ports import (
    InstrumentMetadataProvider,
    InstrumentUniverse,
    MarketDataProvider,
)
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository

logger = logging.getLogger(__name__)

# Top-N size for each explorer highlight leaderboard (gainers/losers/volatile/trending).
_HIGHLIGHT_LIMIT = 5

# Default number of points a sparkline is downsampled to — enough to read a trend without
# shipping a full daily candle series per row.
_DEFAULT_SPARKLINE_POINTS = 24

# Fallback when a symbol is absent from the metadata batch result (no CoinGecko
# mapping, or the whole batch call failed) — every field null, row still present.
_EMPTY_METADATA = InstrumentMetadata(market_cap=None, volume_24h=None, change_7d_pct=None)


class ListEnrichedInstruments:
    """Markets-explorer listing: filter/search/sort/paginate + per-row market & signal data.

    Backs `GET /api/v1/instruments/enriched` (issue #59). Enriches the whole filtered set
    concurrently (`asyncio.gather`) — the curated universe is small (tens of instruments), so
    this keeps the *server* doing one bounded fan-out instead of the frontend firing one
    request per instrument per column (the N+1 pattern #44 warns about). Sorting and
    highlights run over the full enriched set before pagination, so leaderboards and the
    `total` count stay stable as the user pages.

    Reuses `ComputeMarketStats` for the price/change/volatility/candle math (single source of
    that logic) and `SignalRepository.get_latest_for_instrument` for the latest AI signal.
    Every per-instrument enrichment degrades gracefully: a market-data or signal-store failure
    for one row leaves that row's derived fields `None`/empty instead of failing the whole page.

    Read-only (issue #29): this page NEVER triggers an inline LLM run. It serves whatever the
    background refresh job (`RefreshTrackedAnalysis`) has already cached, so a user opening the
    explorer never waits on generation. The signal read is now a single indexed
    `order by created_at desc limit 1` per row, rather than pulling every historical signal
    for a symbol over the wire just to `max()` it down to one.

    `instrument_metadata_provider` (instrument-enrichment spec) supplies the additive
    `market_cap`/`volume_24h`/`change_7d_pct` fields via ONE batch
    `get_metadata_batch(all_symbols)` call per `execute()` — never one call per
    instrument, matching the same bounded-fan-out philosophy as the price/signal
    enrichment above. A symbol absent from the batch result (or the provider failing
    entirely) still leaves that row fully present with all three fields `None`.
    """

    def __init__(
        self,
        instrument_universe: InstrumentUniverse,
        market_data_provider: MarketDataProvider,
        signal_repository: SignalRepository,
        instrument_metadata_provider: InstrumentMetadataProvider,
    ) -> None:
        self._instrument_universe = instrument_universe
        self._market_stats = ComputeMarketStats(
            market_data_provider=market_data_provider, instrument_universe=instrument_universe
        )
        self._signal_repository = signal_repository
        self._instrument_metadata_provider = instrument_metadata_provider

    async def execute(
        self,
        *,
        locale: str,
        asset_class: AssetClass | None = None,
        search: str | None = None,
        sort_by: InstrumentSortField = InstrumentSortField.NAME,
        sort_dir: SortDirection = SortDirection.ASC,
        page: int = 1,
        page_size: int = 20,
        window_days: int = 30,
        sparkline_points: int = _DEFAULT_SPARKLINE_POINTS,
    ) -> InstrumentPage:
        instruments = self._filter(asset_class, search)
        metadata_by_symbol = await self._metadata_batch(instruments)
        enriched = await asyncio.gather(
            *(
                self._enrich(instrument, locale, window_days, sparkline_points, metadata_by_symbol)
                for instrument in instruments
            )
        )

        ordered = _sort(enriched, sort_by, sort_dir)
        start = max(page - 1, 0) * page_size
        items = ordered[start : start + page_size]

        return InstrumentPage(
            items=items,
            total=len(ordered),
            page=page,
            page_size=page_size,
            highlights=_compute_highlights(enriched),
        )

    def _filter(self, asset_class: AssetClass | None, search: str | None) -> list[Instrument]:
        instruments = (
            self._instrument_universe.by_asset_class(asset_class)
            if asset_class
            else self._instrument_universe.all()
        )
        if not search:
            return instruments
        needle = search.strip().casefold()
        return [
            instrument
            for instrument in instruments
            if needle in instrument.symbol.casefold() or needle in instrument.name.casefold()
        ]

    async def _metadata_batch(self, instruments: list[Instrument]) -> dict[str, InstrumentMetadata]:
        """Fetch enrichment metadata for every filtered instrument in ONE batch call.

        A provider failure or an empty result must never break the page: any
        exception degrades to `{}` here too, so every row still gets the
        `_EMPTY_METADATA` default in `_enrich` instead of the whole endpoint
        erroring out (instrument-enrichment spec's "CoinGecko is fully
        unavailable" scenario).
        """
        symbols = [instrument.symbol for instrument in instruments]
        if not symbols:
            return {}
        try:
            return await self._instrument_metadata_provider.get_metadata_batch(symbols)
        except Exception:
            logger.warning("Instrument metadata batch fetch failed; rows omit it.", exc_info=True)
            return {}

    async def _enrich(
        self,
        instrument: Instrument,
        locale: str,
        window_days: int,
        sparkline_points: int,
        metadata_by_symbol: dict[str, InstrumentMetadata],
    ) -> EnrichedInstrument:
        stats = await self._market_stats.execute(instrument.symbol, window_days)
        metadata = metadata_by_symbol.get(instrument.symbol, _EMPTY_METADATA)
        return EnrichedInstrument(
            symbol=instrument.symbol,
            name=instrument.name,
            asset_class=instrument.asset_class,
            currency=instrument.currency,
            last_price=stats.last_price,
            price_delta_pct=stats.price_delta_pct,
            volatility_pct=stats.volatility_pct,
            volatility_regime=stats.volatility_regime,
            sparkline=_downsample_closes(stats.candles, sparkline_points),
            latest_signal=await self._latest_signal(instrument.symbol, locale),
            market_cap=metadata.market_cap,
            volume_24h=metadata.volume_24h,
            change_7d_pct=metadata.change_7d_pct,
        )

    async def _latest_signal(self, symbol: str, locale: str) -> Signal | None:
        try:
            return await self._signal_repository.get_latest_for_instrument(symbol, locale)
        except Exception:
            logger.warning("Signal lookup failed for %s; row omits signal.", symbol, exc_info=True)
            return None


def _downsample_closes(candles: list[PriceCandle], points: int) -> list[float]:
    """Evenly sample up to `points` closing prices (oldest -> newest) for a sparkline."""
    closes = [candle.close for candle in candles]
    if points <= 0 or len(closes) <= points:
        return closes
    step = len(closes) / points
    sampled = [closes[min(int(index * step), len(closes) - 1)] for index in range(points)]
    sampled[-1] = closes[-1]
    return sampled


def _sort(
    enriched: list[EnrichedInstrument], sort_by: InstrumentSortField, sort_dir: SortDirection
) -> list[EnrichedInstrument]:
    reverse = sort_dir is SortDirection.DESC
    if sort_by is InstrumentSortField.NAME:
        return sorted(enriched, key=lambda item: item.name.casefold(), reverse=reverse)

    def value_of(item: EnrichedInstrument) -> float | None:
        return item.last_price if sort_by is InstrumentSortField.PRICE else item.price_delta_pct

    # Rows with no value always sort last, regardless of direction.
    with_value = [item for item in enriched if value_of(item) is not None]
    without_value = [item for item in enriched if value_of(item) is None]
    with_value.sort(key=lambda item: value_of(item) or 0.0, reverse=reverse)
    return with_value + without_value


def _compute_highlights(enriched: list[EnrichedInstrument]) -> InstrumentHighlights:
    gainers = sorted(
        (item for item in enriched if (item.price_delta_pct or 0.0) > 0),
        key=lambda item: item.price_delta_pct or 0.0,
        reverse=True,
    )
    losers = sorted(
        (item for item in enriched if (item.price_delta_pct or 0.0) < 0),
        key=lambda item: item.price_delta_pct or 0.0,
    )
    volatile = sorted(
        (item for item in enriched if item.volatility_pct is not None),
        key=lambda item: item.volatility_pct or 0.0,
        reverse=True,
    )
    trending = sorted(
        (item for item in enriched if item.latest_signal is not None),
        key=lambda item: item.latest_signal.created_at,  # type: ignore[union-attr]
        reverse=True,
    )
    return InstrumentHighlights(
        top_gainers=gainers[:_HIGHLIGHT_LIMIT],
        top_losers=losers[:_HIGHLIGHT_LIMIT],
        most_volatile=volatile[:_HIGHLIGHT_LIMIT],
        trending=trending[:_HIGHLIGHT_LIMIT],
    )
