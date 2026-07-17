import asyncio

from app.application.quant import MarketStats
from app.application.quant.use_cases import ComputeMarketStats
from app.domain.charts.entities import (
    ChartAxis,
    ChartCell,
    ChartMeta,
    ChartRequest,
    ChartRequestKind,
    ChartSpec,
    ChartType,
)
from app.domain.watchlist.ports import WatchlistRepository

# Short window so the heatmap reads as "how are my assets doing today", mirroring
# `get_watchlist_tool`: yesterday's close is the baseline.
_STATS_WINDOW_DAYS = 2


class BuildWatchlistHeatmap:
    """Build a `heatmap` `ChartSpec` of a user's watchlist, one tile per tracked symbol.

    Each tile's `value` is the symbol's recent % change (`ComputeMarketStats`), so the grid
    colors green for gainers and red for losers at a glance. Reads EVERY watchlist the user
    owns and de-duplicates symbols across them. SECURITY: `user_id` is the authenticated
    caller's id (the render tool takes it from the run config, never from model arguments),
    so a turn can only ever heatmap the user's own watchlists.

    Returns a spec with empty `cells` when the user tracks nothing (or no symbol has usable
    price data); the caller (`render_watchlist_heatmap` tool) treats that as 'nothing to
    show' and emits no chart. `source` cites both real vendors, since a watchlist can mix
    crypto and equities."""

    def __init__(
        self,
        watchlist_repository: WatchlistRepository,
        compute_market_stats: ComputeMarketStats,
        market_source_crypto: str,
        market_source_equity: str,
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._compute_market_stats = compute_market_stats
        self._market_source_crypto = market_source_crypto
        self._market_source_equity = market_source_equity

    async def execute(self, user_id: str) -> ChartSpec:
        watchlists = await self._watchlist_repository.list_for_user(user_id)
        symbols: list[str] = []
        for watchlist in watchlists:
            items = await self._watchlist_repository.list_items(watchlist.id)
            symbols.extend(item.symbol for item in items)
        symbols = list(dict.fromkeys(symbols))

        stats_by_symbol = await self._stats_for(symbols)
        cells = [
            ChartCell(label=symbol, value=round(stats_by_symbol[symbol].price_delta_pct or 0.0, 2))
            for symbol in symbols
            if symbol in stats_by_symbol and stats_by_symbol[symbol].price_delta_pct is not None
        ]

        return ChartSpec(
            type=ChartType.HEATMAP,
            series=[],
            cells=cells,
            x_axis=ChartAxis(label="", type="category"),
            y_axis=ChartAxis(label="", type="value", format="percent"),
            meta=ChartMeta(
                title="Watchlist heatmap",
                subtitle=f"Last {_STATS_WINDOW_DAYS} day(s)",
                source=f"{self._market_source_crypto} / {self._market_source_equity}",
                timeframe=f"{_STATS_WINDOW_DAYS}d",
                request=ChartRequest(
                    kind=ChartRequestKind.WATCHLIST_HEATMAP,
                    symbols=[cell.label for cell in cells],
                    timeframe=f"{_STATS_WINDOW_DAYS}d",
                ),
            ),
        )

    async def _stats_for(self, symbols: list[str]) -> dict[str, MarketStats]:
        """Fetch a bounded concurrent stats snapshot; a failed symbol is simply absent."""

        async def _one(symbol: str) -> tuple[str, MarketStats | None]:
            try:
                return symbol, await self._compute_market_stats.execute(symbol, _STATS_WINDOW_DAYS)
            except Exception:  # noqa: BLE001 — one dark symbol must not blank the whole heatmap
                return symbol, None

        results = await asyncio.gather(*(_one(symbol) for symbol in symbols))
        return {symbol: stats for symbol, stats in results if stats is not None}
