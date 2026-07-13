import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from app.application.analysis.refresh_result import RefreshResult
from app.application.sentiment.use_cases import AnalyzeSentiment
from app.application.signals.use_cases import GenerateSignal
from app.domain.watchlist.ports import WatchlistRepository

logger = logging.getLogger(__name__)


class RefreshTrackedAnalysis:
    """Keep every watchlisted instrument's shared analysis warm, off the request path (#29).

    The other half of the freshness cache. The gate in `GenerateSignal`/`AnalyzeSentiment`
    stops redundant LLM runs, but on its own it would just move the cost to whoever happens to
    make the first request after a TTL expires — that user pays the full pipeline latency
    inline. This pass runs on the existing Watchdog scheduler and refreshes analysis *before*
    anyone asks for it, so user reads (radar, explorer, briefings) only ever serve cached rows.

    Deliberately calls the generate use cases with `force=False`: each is already freshness-
    gated, so a tick over still-fresh instruments is a handful of cheap indexed SELECTs and
    zero LLM calls. That's what lets the tick run every few minutes without the TTLs and the
    cadence having to be kept in sync — the TTL decides staleness, the tick just asks.

    Per-`(symbol, locale)` isolation: one instrument's failure (an unknown symbol, a news
    provider timeout, a store blip) must never abort the rest of the pass, exactly like
    `AnalyzePendingNews`'s per-group isolation. Concurrency is bounded so a large watchlist
    union can't fan out unbounded concurrent LLM requests.

    Also seeds a single symbol on demand (`execute(symbols=[...])`) — used when a watchlist item
    is added for an instrument nobody was tracking yet, so the radar isn't empty until the next
    scheduled tick.
    """

    def __init__(
        self,
        watchlist_repository: WatchlistRepository,
        generate_signal: GenerateSignal,
        analyze_sentiment: AnalyzeSentiment,
        locales: list[str],
        max_concurrency: int,
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._generate_signal = generate_signal
        self._analyze_sentiment = analyze_sentiment
        self._locales = locales
        self._max_concurrency = max(1, max_concurrency)

    async def execute(self, symbols: list[str] | None = None) -> RefreshResult:
        """Refresh analysis for `symbols`, or for every watchlisted instrument when omitted."""
        targets = symbols if symbols is not None else await self._tracked_symbols()
        if not targets or not self._locales:
            return RefreshResult(
                symbols=len(targets), locales=len(self._locales), refreshed=0, failed=0
            )

        semaphore = asyncio.Semaphore(self._max_concurrency)
        outcomes = await asyncio.gather(
            *(
                self._refresh_one(symbol, locale, semaphore)
                for symbol in targets
                for locale in self._locales
            )
        )
        refreshed = sum(1 for ok in outcomes if ok)
        return RefreshResult(
            symbols=len(targets),
            locales=len(self._locales),
            refreshed=refreshed,
            failed=len(outcomes) - refreshed,
        )

    async def _tracked_symbols(self) -> list[str]:
        """The de-duplicated union of every symbol on every watchlist.

        Global, not user-scoped — analysis is shared, so one refresh of AAPL serves every user
        tracking it. Sorted purely to make the pass deterministic and its logs readable.
        """
        watchlists = await self._watchlist_repository.list_all()
        symbols: set[str] = set()
        for watchlist in watchlists:
            for item in await self._watchlist_repository.list_items(watchlist.id):
                symbols.add(item.symbol.upper())
        return sorted(symbols)

    async def _refresh_one(self, symbol: str, locale: str, semaphore: asyncio.Semaphore) -> bool:
        """Refresh one `(symbol, locale)`; return whether any half of it succeeded.

        Signal and sentiment are refreshed independently: a sentiment failure shouldn't throw
        away a signal that generated fine, so each is isolated and the pair only counts as
        failed when BOTH halves failed.
        """
        async with semaphore:
            signal_ok = await self._isolated(
                self._generate_signal.execute(symbol, locale), "signal", symbol, locale
            )
            sentiment_ok = await self._isolated(
                self._analyze_sentiment.execute(symbol, locale), "sentiment", symbol, locale
            )
            return signal_ok or sentiment_ok

    @staticmethod
    async def _isolated(
        awaitable: Coroutine[Any, Any, object], kind: str, symbol: str, locale: str
    ) -> bool:
        """Await one refresh, swallowing (but logging) any failure. The scheduler tick must
        never die because one instrument's news provider timed out."""
        try:
            await awaitable
        except Exception:
            logger.warning(
                "Refreshing %s for %s (%s) failed; continuing with the rest of the pass.",
                kind,
                symbol,
                locale,
                exc_info=True,
            )
            return False
        return True
