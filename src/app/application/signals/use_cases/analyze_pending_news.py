import asyncio
import logging
from collections import defaultdict

from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.compliance import ComplianceViolationError
from app.application.signals.insufficient_evidence_error import InsufficientEvidenceError
from app.application.signals.unknown_instrument_error import UnknownInstrumentError
from app.application.signals.use_cases.analyze_pending_news_result import (
    AnalyzePendingNewsResult,
)
from app.application.signals.use_cases.compute_news_relevance_score import (
    compute_news_relevance_score,
)
from app.application.signals.use_cases.generate_signal import GenerateSignal
from app.application.signals.use_cases.normalize_news_title import normalize_news_title
from app.domain.agents.ports import LLMProvider
from app.domain.market.entities import AnalysisStatus, Instrument, NewsItem
from app.domain.market.ports import (
    InstrumentUniverse,
    MarketDataProvider,
    NewsItemRepository,
    NewsProvider,
)
from app.domain.signals.ports import SignalRepository

logger = logging.getLogger(__name__)


class AnalyzePendingNews:
    """Batch/background Analyst pipeline (issue #2): analyzes every persisted `news_items`
    row with `analysis_status = pending` server-side, replacing the N-sequential HTTP
    calls the frontend previously had to make one instrument at a time
    (`radar-store.ts`'s `generateAllUnclassified()`).

    Groups pending items by their first linked instrument symbol — an item with no
    linked symbol can't be analyzed against any instrument and is marked `skipped`
    outright. Within each symbol group, a cheap pre-filter (issue #3:
    `compute_news_relevance_score` + duplicate-title detection via
    `normalize_news_title`) decides which items are worth an LLM call before running the
    existing `GenerateSignal` pipeline once per remaining symbol — bounded by an
    `asyncio.Semaphore(max_concurrency)` so a large backlog can't fan out an unbounded
    number of concurrent LLM calls — and persists every item's outcome back onto
    `news_items` (`analysis_status`/`signal_id`).

    Deliberately reuses `GenerateSignal` rather than re-implementing classification: it
    already owns the evidence-floor check, LLM classification, historical-analogs RAG,
    and the compliance gate. A `GenerateSignal.execute` failure is caught per-symbol so
    one bad group never aborts the whole batch; those items are left `pending` (not
    `skipped` — that's a triage decision, not a failure) to be retried on the next run.
    """

    def __init__(
        self,
        news_item_repository: NewsItemRepository,
        instrument_universe: InstrumentUniverse,
        market_data_provider: MarketDataProvider,
        news_provider: NewsProvider,
        signal_repository: SignalRepository,
        llm_provider: LLMProvider,
        find_historical_analogs: FindHistoricalAnalogs,
        index_signal_analog: IndexSignalAnalog,
        min_distinct_sources: int,
        relevance_skip_threshold: float,
        max_concurrency: int,
        batch_limit: int,
    ) -> None:
        self._news_item_repository = news_item_repository
        self._instrument_universe = instrument_universe
        self._market_data_provider = market_data_provider
        self._news_provider = news_provider
        self._signal_repository = signal_repository
        self._llm_provider = llm_provider
        self._find_historical_analogs = find_historical_analogs
        self._index_signal_analog = index_signal_analog
        self._min_distinct_sources = min_distinct_sources
        self._relevance_skip_threshold = relevance_skip_threshold
        self._batch_limit = batch_limit
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(self, locale: str) -> AnalyzePendingNewsResult:
        pending = await self._news_item_repository.list_pending(limit=self._batch_limit)
        if not pending:
            return AnalyzePendingNewsResult(analyzed_count=0, skipped_count=0, failed_count=0)

        groups: dict[str, list[NewsItem]] = defaultdict(list)
        no_symbol_skipped = 0
        for item in pending:
            if not item.related_symbols:
                await self._mark_skipped(item)
                no_symbol_skipped += 1
                continue
            groups[item.related_symbols[0].upper()].append(item)

        results = await asyncio.gather(
            *(self._analyze_symbol_group(symbol, items, locale) for symbol, items in groups.items())
        )

        analyzed_count = sum(result[0] for result in results)
        skipped_count = no_symbol_skipped + sum(result[1] for result in results)
        failed_count = sum(result[2] for result in results)

        logger.info(
            "AnalyzePendingNews: %d pending news item(s) -> %d analyzed, %d skipped "
            "(pre-filter/duplicate/no linked instrument), %d failed (left pending for retry)",
            len(pending),
            analyzed_count,
            skipped_count,
            failed_count,
        )
        return AnalyzePendingNewsResult(
            analyzed_count=analyzed_count, skipped_count=skipped_count, failed_count=failed_count
        )

    async def _analyze_symbol_group(
        self, symbol: str, items: list[NewsItem], locale: str
    ) -> tuple[int, int, int]:
        instrument = self._instrument_universe.by_symbol(symbol)
        to_classify, prefiltered_out = self._prefilter(instrument, items)
        for item in prefiltered_out:
            await self._mark_skipped(item)

        if not to_classify:
            return 0, len(prefiltered_out), 0

        async with self._semaphore:
            try:
                generate_signal = GenerateSignal(
                    news_provider=self._news_provider,
                    market_data_provider=self._market_data_provider,
                    instrument_universe=self._instrument_universe,
                    signal_repository=self._signal_repository,
                    llm_provider=self._llm_provider,
                    find_historical_analogs=self._find_historical_analogs,
                    index_signal_analog=self._index_signal_analog,
                    min_distinct_sources=self._min_distinct_sources,
                )
                signal = await generate_signal.execute(symbol, locale)
            except (UnknownInstrumentError, InsufficientEvidenceError, ComplianceViolationError):
                logger.info(
                    "AnalyzePendingNews: %s not classified this run (%d item(s) left pending).",
                    symbol,
                    len(to_classify),
                )
                return 0, len(prefiltered_out), len(to_classify)
            except Exception:
                logger.exception(
                    "AnalyzePendingNews: unexpected failure classifying %s "
                    "(%d item(s) left pending).",
                    symbol,
                    len(to_classify),
                )
                return 0, len(prefiltered_out), len(to_classify)

        for item in to_classify:
            await self._mark_analyzed(item, signal.id)
        return len(to_classify), len(prefiltered_out), 0

    def _prefilter(
        self, instrument: Instrument | None, items: list[NewsItem]
    ) -> tuple[list[NewsItem], list[NewsItem]]:
        """Issue #3: split `items` into (worth-an-LLM-call, skip-without-one) before any
        LLM classification happens. Skips items below `relevance_skip_threshold` and every
        item after the first with the same normalized title within this group (a
        near-duplicate wire story already covering the same event for this instrument).
        """
        to_classify: list[NewsItem] = []
        skipped: list[NewsItem] = []
        seen_titles: set[str] = set()
        for item in items:
            normalized_title = normalize_news_title(item.title)
            if normalized_title in seen_titles:
                skipped.append(item)
                continue
            if instrument is not None:
                score = compute_news_relevance_score(item, instrument)
                if score < self._relevance_skip_threshold:
                    skipped.append(item)
                    continue
            seen_titles.add(normalized_title)
            to_classify.append(item)
        return to_classify, skipped

    async def _mark_skipped(self, item: NewsItem) -> None:
        await self._news_item_repository.update_analysis_status(item.id, AnalysisStatus.SKIPPED)

    async def _mark_analyzed(self, item: NewsItem, signal_id: str) -> None:
        await self._news_item_repository.update_analysis_status(
            item.id, AnalysisStatus.ANALYZED, signal_id=signal_id
        )
