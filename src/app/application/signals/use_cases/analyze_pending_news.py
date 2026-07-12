import asyncio
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime

from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.compliance import ComplianceViolationError
from app.application.signals.insufficient_evidence_error import InsufficientEvidenceError
from app.application.signals.news_prefilter_policy import NewsPrefilterPolicy
from app.application.signals.unknown_instrument_error import UnknownInstrumentError
from app.application.signals.use_cases.analyze_pending_news_result import (
    AnalyzePendingNewsResult,
)
from app.application.signals.use_cases.compute_news_materiality_score import (
    compute_news_materiality_score,
)
from app.application.signals.use_cases.compute_news_relevance_score import (
    compute_news_relevance_score,
)
from app.application.signals.use_cases.generate_signal import GenerateSignal
from app.application.signals.use_cases.normalize_news_title import normalize_news_title
from app.domain.agents.ports import LLMProvider
from app.domain.market.entities import AnalysisStatus, Instrument, NewsItem, NewsSkipReason
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
    linked symbol can't be analyzed against any instrument (`GenerateSignal` is per-symbol)
    and is marked `skipped`/`no_linked_instrument` outright. Within each symbol group, a
    cheap pre-filter (issue #3/#26: a `NewsPrefilterPolicy`-weighted blend of
    `compute_news_relevance_score` and `compute_news_materiality_score`, plus duplicate-title
    detection via `normalize_news_title`) decides which items are worth an LLM call before
    running the existing `GenerateSignal` pipeline once per remaining symbol — bounded by an
    `asyncio.Semaphore(max_concurrency)` so a large backlog can't fan out an unbounded number
    of concurrent LLM calls — and persists every item's outcome back onto `news_items`
    (`analysis_status`/`signal_id`/`skip_reason`).

    Deliberately reuses `GenerateSignal` rather than re-implementing classification: it
    already owns the evidence-floor check, LLM classification, historical-analogs RAG,
    and the compliance gate. A `GenerateSignal.execute` failure is caught per-symbol so
    one bad group never aborts the whole batch.

    Every non-`analyzed` outcome now persists a `NewsSkipReason` (issue #26) instead of leaving
    the item in an unexplained `pending`/`skipped` state that the UI could only render as the
    ambiguous "Sin clasificar" tag. The reason also decides whether an item is retried:

    - Retryable (left `pending`): `insufficient_evidence` (more sources may arrive, and the
      floor is checked before any LLM call, so a retry is cheap) and `analysis_failed` (a
      transient LLM/store failure).
    - Terminal (marked `skipped`): `no_linked_instrument`, `gated_low_relevance`,
      `near_duplicate`, and `compliance_blocked` — the last of these because retrying it every
      tick would burn a full LLM call on output that is very likely to be rejected again.
      An unknown symbol is terminal too: it is `no_linked_instrument` in practice, and used to
      be caught as an `UnknownInstrumentError` *after* `GenerateSignal` had already been
      entered, leaving its items `pending` and re-attempted on every single tick, forever.
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
        prefilter_policy: NewsPrefilterPolicy,
        min_distinct_sources: int,
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
        self._prefilter_policy = prefilter_policy
        self._min_distinct_sources = min_distinct_sources
        self._batch_limit = batch_limit
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(self, locale: str) -> AnalyzePendingNewsResult:
        pending = await self._news_item_repository.list_pending(limit=self._batch_limit)
        if not pending:
            return AnalyzePendingNewsResult(analyzed_count=0, skipped_count=0, failed_count=0)

        # One clock for the whole run, so two items published seconds apart can't be scored
        # against two different "now"s and land on opposite sides of the threshold.
        now = datetime.now(UTC)

        skipped_by_reason: Counter[NewsSkipReason] = Counter()
        failed_by_reason: Counter[NewsSkipReason] = Counter()

        groups: dict[str, list[NewsItem]] = defaultdict(list)
        for item in pending:
            if not item.related_symbols:
                await self._mark_skipped(item, NewsSkipReason.NO_LINKED_INSTRUMENT)
                skipped_by_reason[NewsSkipReason.NO_LINKED_INSTRUMENT] += 1
                continue
            groups[item.related_symbols[0].upper()].append(item)

        results = await asyncio.gather(
            *(
                self._analyze_symbol_group(symbol, items, locale, now)
                for symbol, items in groups.items()
            )
        )

        analyzed_count = 0
        for group_analyzed, group_skipped, group_failed in results:
            analyzed_count += group_analyzed
            skipped_by_reason += group_skipped
            failed_by_reason += group_failed

        skipped_count = sum(skipped_by_reason.values())
        failed_count = sum(failed_by_reason.values())

        logger.info(
            "AnalyzePendingNews: %d pending news item(s) -> %d analyzed, %d skipped, "
            "%d failed (left pending for retry). Skipped by reason: %s. Failed by reason: %s.",
            len(pending),
            analyzed_count,
            skipped_count,
            failed_count,
            _format_breakdown(skipped_by_reason),
            _format_breakdown(failed_by_reason),
        )
        return AnalyzePendingNewsResult(
            analyzed_count=analyzed_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            skipped_by_reason=_to_reason_counts(skipped_by_reason),
            failed_by_reason=_to_reason_counts(failed_by_reason),
        )

    async def _analyze_symbol_group(
        self, symbol: str, items: list[NewsItem], locale: str, now: datetime
    ) -> tuple[int, Counter[NewsSkipReason], Counter[NewsSkipReason]]:
        """Returns `(analyzed_count, skipped_by_reason, failed_by_reason)` for one symbol."""
        instrument = self._instrument_universe.by_symbol(symbol)
        if instrument is None:
            # Nothing to classify this group against, and no amount of retrying will conjure
            # the instrument into the universe. Terminal, not a failure — see the class
            # docstring's retryable/terminal split.
            logger.info(
                "AnalyzePendingNews: %s is not in the instrument universe; "
                "marking %d item(s) as no_linked_instrument.",
                symbol,
                len(items),
            )
            unlinked = await self._mark_all_skipped(items, NewsSkipReason.NO_LINKED_INSTRUMENT)
            return 0, unlinked, Counter()

        to_classify, prefiltered_out = self._prefilter(instrument, items, now)
        skipped: Counter[NewsSkipReason] = Counter()
        for item, reason in prefiltered_out:
            await self._mark_skipped(item, reason)
            skipped[reason] += 1

        if not to_classify:
            return 0, skipped, Counter()

        async with self._semaphore:
            try:
                signal = await self._build_generate_signal().execute(symbol, locale)
            except InsufficientEvidenceError:
                logger.info(
                    "AnalyzePendingNews: %s has too few distinct news sources to classify; "
                    "%d item(s) left pending for retry.",
                    symbol,
                    len(to_classify),
                )
                thin = await self._mark_all_pending(
                    to_classify, NewsSkipReason.INSUFFICIENT_EVIDENCE
                )
                return 0, skipped, thin
            except ComplianceViolationError:
                logger.warning(
                    "AnalyzePendingNews: %s classification failed the compliance gate; "
                    "%d item(s) marked compliance_blocked (not retried).",
                    symbol,
                    len(to_classify),
                )
                skipped += await self._mark_all_skipped(
                    to_classify, NewsSkipReason.COMPLIANCE_BLOCKED
                )
                return 0, skipped, Counter()
            except UnknownInstrumentError:
                # Defensive: `by_symbol` already returned an instrument above, so this can only
                # fire if the universe changed under us mid-run. Same terminal handling.
                skipped += await self._mark_all_skipped(
                    to_classify, NewsSkipReason.NO_LINKED_INSTRUMENT
                )
                return 0, skipped, Counter()
            except Exception:
                logger.exception(
                    "AnalyzePendingNews: unexpected failure classifying %s "
                    "(%d item(s) left pending for retry).",
                    symbol,
                    len(to_classify),
                )
                failed = await self._mark_all_pending(to_classify, NewsSkipReason.ANALYSIS_FAILED)
                return 0, skipped, failed

        for item in to_classify:
            await self._mark_analyzed(item, signal.id)
        return len(to_classify), skipped, Counter()

    def _build_generate_signal(self) -> GenerateSignal:
        return GenerateSignal(
            news_provider=self._news_provider,
            market_data_provider=self._market_data_provider,
            instrument_universe=self._instrument_universe,
            signal_repository=self._signal_repository,
            llm_provider=self._llm_provider,
            find_historical_analogs=self._find_historical_analogs,
            index_signal_analog=self._index_signal_analog,
            min_distinct_sources=self._min_distinct_sources,
        )

    def _prefilter(
        self, instrument: Instrument, items: list[NewsItem], now: datetime
    ) -> tuple[list[NewsItem], list[tuple[NewsItem, NewsSkipReason]]]:
        """Split `items` into (worth-an-LLM-call, skip-without-one — each with the reason it
        was skipped) before any LLM classification happens (issues #3 and #26).

        Two gates, cheapest first:

        1. **Near-duplicate** — every item after the first with the same normalized title
           within this group is a wire story already covering the same event for this
           instrument.
        2. **Combined relevance + materiality** — `NewsPrefilterPolicy`'s weighted blend of
           "is this about this instrument?" and "is this important?", skipped below
           `skip_threshold`. Blending is what lets a materially-important article that never
           spells out the ticker survive, which symbol-relevance alone could not.
        """
        policy = self._prefilter_policy
        weight_total = policy.relevance_weight + policy.materiality_weight
        to_classify: list[NewsItem] = []
        skipped: list[tuple[NewsItem, NewsSkipReason]] = []
        seen_titles: set[str] = set()

        for item in items:
            normalized_title = normalize_news_title(item.title)
            if normalized_title in seen_titles:
                skipped.append((item, NewsSkipReason.NEAR_DUPLICATE))
                continue

            relevance = compute_news_relevance_score(item, instrument, policy.name_match_score)
            materiality = compute_news_materiality_score(item, policy, now)
            score = (
                (policy.relevance_weight * relevance + policy.materiality_weight * materiality)
                / weight_total
                if weight_total > 0
                else 0.0
            )
            if score < policy.skip_threshold:
                logger.debug(
                    "AnalyzePendingNews: gating %r out for %s "
                    "(relevance=%.2f, materiality=%.2f, score=%.2f < %.2f)",
                    item.title,
                    instrument.symbol,
                    relevance,
                    materiality,
                    score,
                    policy.skip_threshold,
                )
                skipped.append((item, NewsSkipReason.GATED_LOW_RELEVANCE))
                continue

            seen_titles.add(normalized_title)
            to_classify.append(item)

        return to_classify, skipped

    async def _mark_all_skipped(
        self, items: list[NewsItem], reason: NewsSkipReason
    ) -> Counter[NewsSkipReason]:
        for item in items:
            await self._mark_skipped(item, reason)
        return Counter({reason: len(items)})

    async def _mark_all_pending(
        self, items: list[NewsItem], reason: NewsSkipReason
    ) -> Counter[NewsSkipReason]:
        """Leave the items `pending` (so the next run retries them) but record *why* this run
        produced nothing, so the UI can explain the gap instead of showing "Sin clasificar"."""
        for item in items:
            await self._news_item_repository.update_analysis_status(
                item.id, AnalysisStatus.PENDING, skip_reason=reason
            )
        return Counter({reason: len(items)})

    async def _mark_skipped(self, item: NewsItem, reason: NewsSkipReason) -> None:
        await self._news_item_repository.update_analysis_status(
            item.id, AnalysisStatus.SKIPPED, skip_reason=reason
        )

    async def _mark_analyzed(self, item: NewsItem, signal_id: str) -> None:
        await self._news_item_repository.update_analysis_status(
            item.id, AnalysisStatus.ANALYZED, signal_id=signal_id
        )


def _to_reason_counts(counter: Counter[NewsSkipReason]) -> dict[str, int]:
    return {reason.value: count for reason, count in counter.items()}


def _format_breakdown(counter: Counter[NewsSkipReason]) -> str:
    if not counter:
        return "none"
    return ", ".join(
        f"{reason.value}={count}" for reason, count in sorted(counter.items(), key=_by_reason_value)
    )


def _by_reason_value(entry: tuple[NewsSkipReason, int]) -> str:
    return entry[0].value
