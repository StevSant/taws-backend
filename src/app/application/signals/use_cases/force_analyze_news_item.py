import logging

from app.application.compliance import ComplianceViolationError
from app.application.signals.insufficient_evidence_error import InsufficientEvidenceError
from app.application.signals.news_item_not_analyzable_error import NewsItemNotAnalyzableError
from app.application.signals.news_item_not_found_error import NewsItemNotFoundError
from app.application.signals.unknown_instrument_error import UnknownInstrumentError
from app.application.signals.use_cases.generate_signal import GenerateSignal
from app.domain.market.entities import AnalysisStatus, NewsItem, NewsSkipReason
from app.domain.market.ports import NewsItemRepository

logger = logging.getLogger(__name__)


class ForceAnalyzeNewsItem:
    """Manual "Analizar ahora": force-classify ONE news item, bypassing the pre-filter (#27).

    The counterpart to `AnalyzePendingNews`'s gate. The gate exists to save tokens by default;
    this is the human's escape hatch to spend one on an item they judge important, and it is
    what backs `POST /api/v1/news/{news_id}/analyze`. Neither existing entry point could do
    this: `POST /signals/generate` is per-instrument-symbol and can't target one article, and
    `POST /news/analyze-pending` is batch and *deliberately* skips the low-relevance item the
    user is looking at.

    Bypassing `_prefilter` is the entire point — but it stops there. The evidence floor
    (`InsufficientEvidenceError`) and the compliance gate (`ComplianceViolationError`) inside
    `GenerateSignal` still apply: those are correctness guarantees, not cost optimizations, and
    a user asking for analysis is not authorization to ship a thinly-sourced or non-compliant
    signal. Classification itself is reused wholesale from `GenerateSignal`, never
    re-implemented.

    Every outcome — success or not — is persisted onto the item (`analysis_status` +
    `skip_reason`, issue #26) before returning, so the news-detail page re-renders the real
    state rather than an optimistic guess.

    Empty `related_symbols` edge case: `GenerateSignal` is per-symbol, so an article linked to
    no instrument simply cannot be classified. Rather than inventing an instrument picker, this
    persists `no_linked_instrument` and raises `NewsItemNotAnalyzableError` — the router turns
    that into a 4xx carrying the reason, and the frontend disables the button with an
    explanation instead of offering an action that cannot succeed.
    """

    def __init__(
        self,
        news_item_repository: NewsItemRepository,
        generate_signal: GenerateSignal,
    ) -> None:
        self._news_item_repository = news_item_repository
        self._generate_signal = generate_signal

    async def execute(self, news_id: str, locale: str) -> NewsItem:
        item = await self._news_item_repository.get_by_id(news_id)
        if item is None:
            raise NewsItemNotFoundError(news_id)

        if not item.related_symbols:
            raise await self._reject(
                item,
                AnalysisStatus.SKIPPED,
                NewsSkipReason.NO_LINKED_INSTRUMENT,
                "This article is not linked to any instrument in the universe, and signals are "
                "generated per instrument — there is nothing to classify it against.",
            )

        symbol = item.related_symbols[0].upper()
        try:
            # `force=True` (issue #29): `GenerateSignal` is freshness-gated now, and this is
            # the ONE call site that must never be served from cache. The user pressed
            # "Analizar ahora" on an article the batch gate deliberately skipped — handing
            # back a cached signal generated minutes ago from *other* news would leave the
            # button looking broken and the article still unexplained. Forcing here is safe:
            # it's an explicit human action, not an unauthenticated cache-bust vector.
            signal = await self._generate_signal.execute(symbol, locale, force=True)
        except UnknownInstrumentError:
            raise await self._reject(
                item,
                AnalysisStatus.SKIPPED,
                NewsSkipReason.NO_LINKED_INSTRUMENT,
                f"{symbol} is not in the instrument universe, so this article cannot be "
                "classified against it.",
            ) from None
        except InsufficientEvidenceError as exc:
            raise await self._reject(
                item,
                AnalysisStatus.PENDING,
                NewsSkipReason.INSUFFICIENT_EVIDENCE,
                str(exc),
            ) from None
        except ComplianceViolationError:
            raise await self._reject(
                item,
                AnalysisStatus.SKIPPED,
                NewsSkipReason.COMPLIANCE_BLOCKED,
                f"The generated analysis for {symbol} did not pass the compliance review, so no "
                "signal was persisted.",
            ) from None

        logger.info(
            "ForceAnalyzeNewsItem: news item %s force-classified against %s -> signal %s",
            item.id,
            symbol,
            signal.id,
        )
        return await self._news_item_repository.update_analysis_status(
            item.id, AnalysisStatus.ANALYZED, signal_id=signal.id
        )

    async def _reject(
        self,
        item: NewsItem,
        status: AnalysisStatus,
        reason: NewsSkipReason,
        message: str,
    ) -> NewsItemNotAnalyzableError:
        """Persist why this item can't be analyzed, then build the error for the caller to
        raise. `PENDING` is used for the retryable reason (`insufficient_evidence`) and
        `SKIPPED` for the terminal ones — the same split `AnalyzePendingNews` makes, so a
        manual attempt and a batch attempt never leave the item in contradictory states.
        """
        logger.info("ForceAnalyzeNewsItem: news item %s not analyzable (%s)", item.id, reason.value)
        await self._news_item_repository.update_analysis_status(item.id, status, skip_reason=reason)
        return NewsItemNotAnalyzableError(item.id, reason, message)
