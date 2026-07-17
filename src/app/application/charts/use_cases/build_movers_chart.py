from app.application.instruments.use_cases import ListEnrichedInstruments
from app.domain.charts.entities import (
    ChartAxis,
    ChartMeta,
    ChartPoint,
    ChartRequest,
    ChartRequestKind,
    ChartSeries,
    ChartSpec,
    ChartType,
)
from app.domain.market.entities import AssetClass


class BuildMoversChart:
    """Build a `bar` `ChartSpec` of the tracked universe's top movers (gainers + losers).

    Reuses `ListEnrichedInstruments` — the SAME use case that powers the `get_market_movers`
    tool and the markets explorer — so the chart and the text ranking can never disagree.
    The gainers and losers highlight groups are merged and sorted descending by % change, so
    the bar chart reads left-to-right from biggest gainer to biggest loser (colored by sign
    in the renderer/mapper).

    `source` cites both real vendors (CoinGecko for crypto, Yahoo Finance otherwise), since a
    whole-universe ranking spans both — unless restricted to one asset class, when it cites
    just that class's vendor. Returns a spec with empty `series[0].points` when no row has a
    usable % change; the caller (`render_market_movers_chart` tool) treats that as
    'unavailable' and emits no chart."""

    def __init__(
        self,
        list_enriched_instruments: ListEnrichedInstruments,
        market_source_crypto: str,
        market_source_equity: str,
    ) -> None:
        self._list_enriched_instruments = list_enriched_instruments
        self._market_source_crypto = market_source_crypto
        self._market_source_equity = market_source_equity

    async def execute(
        self, locale: str, window_days: int = 2, asset_class: AssetClass | None = None
    ) -> ChartSpec:
        page = await self._list_enriched_instruments.execute(
            locale=locale,
            asset_class=asset_class,
            page=1,
            page_size=1,
            window_days=window_days,
        )
        movers = [
            item
            for item in (*page.highlights.top_gainers, *page.highlights.top_losers)
            if item.price_delta_pct is not None
        ]
        movers.sort(key=lambda item: item.price_delta_pct or 0.0, reverse=True)
        points = [
            ChartPoint(x=item.symbol, y=round(item.price_delta_pct or 0.0, 2)) for item in movers
        ]

        return ChartSpec(
            type=ChartType.BAR,
            series=[ChartSeries(name="Top movers", points=points)],
            x_axis=ChartAxis(label="Instrument", type="category"),
            y_axis=ChartAxis(label="Change %", type="value", format="percent"),
            meta=ChartMeta(
                title="Top movers",
                subtitle=f"Last {window_days} day(s)",
                source=self._source_for(asset_class),
                timeframe=f"{window_days}d",
                request=ChartRequest(
                    kind=ChartRequestKind.MARKET_MOVERS,
                    symbols=[item.symbol for item in movers],
                    timeframe=f"{window_days}d",
                ),
            ),
        )

    def _source_for(self, asset_class: AssetClass | None) -> str:
        if asset_class is AssetClass.CRYPTO:
            return self._market_source_crypto
        if asset_class is not None:
            return self._market_source_equity
        return f"{self._market_source_crypto} / {self._market_source_equity}"
