import logging
import uuid

from app.application.common import build_locale_instruction
from app.application.sentiment.sentiment_classification import SentimentClassification
from app.application.sentiment.unknown_instrument_error import UnknownInstrumentError
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.freshness import FreshnessPolicy
from app.domain.market.entities import Instrument, NewsItem
from app.domain.market.ports import InstrumentUniverse, NewsProvider
from app.domain.sentiment.entities import SentimentLabel, SentimentReading
from app.domain.sentiment.ports import FearGreedProvider, SentimentRepository
from app.domain.signals.entities import SignalEvidence

logger = logging.getLogger(__name__)

_CLASSIFICATION_SCHEMA_NAME = "sentiment_classification"

_CLASSIFICATION_SYSTEM_PROMPT = """You are the Sentiment Analyst — a market-intelligence agent \
that scores the news tone for a single financial instrument.

Given an instrument and a list of dated, sourced recent news items, produce a tone score from \
-1.0 (very negative) to +1.0 (very positive) summarizing the overall tone of the coverage. \
Ground the score strictly in the provided news items — never invent facts, sources, or events \
that aren't in them. If there is no meaningful news, or the coverage is mixed/inconclusive, \
prefer a score near 0.0 over guessing a direction.

This is research/informational output only — never trading instructions, and never phrased as \
personalized advice."""

_FALLBACK_REASONING = "fallback tone score (structured output unavailable)"


class AnalyzeSentiment:
    """Sentiment Analyst pipeline (issue #21): recent news -> LLM-scored tone, combined with
    the current market-wide Fear & Greed Index reading, into one `SentimentReading` per
    instrument.

    Deliberately NOT built on `AgentRunner` — same rationale as `GenerateConsequenceChain`/
    `GenerateSignal`: a plain application-layer use case (constructor-injected with
    `NewsProvider`, `FearGreedProvider`, `InstrumentUniverse`, and `LLMProvider`) fits a
    single-call "instrument in, structured reading out" pipeline better than the
    chat/SSE-shaped `AgentRunner` contract. Reused as-is by the `sentiment` chat
    specialist's tool (`infrastructure/agents/tools/analyze_sentiment_tool.py`) and by
    `POST /api/v1/sentiment/{symbol}/analyze` (`api/v1/routers/sentiment.py`).

    Tone scale: `-1.0..1.0`, the same scale `domain/market/entities/news_item.py`'s
    `NewsItem.sentiment_score` already uses (Marketaux's entity-sentiment enrichment) —
    chosen for consistency rather than introducing a second sentiment scale into the
    codebase. `tone_label` (`SentimentLabel`) is deterministically bucketed from
    `tone_score` via `Settings.sentiment_bullish_threshold`/`sentiment_bearish_threshold`
    (see `_bucket_tone_label` below), never chosen by the model directly — same
    "deterministic bucketing next to a raw model/vendor number" discipline as
    `infrastructure/macro/bucket_volatility_regime.py` bucketing VIX.

    Fear & Greed reading: alternative.me's index is market-wide, not per-instrument (see
    `FearGreedReading`'s docstring), so the same current reading is attached to every
    instrument's `SentimentReading` as sentiment *context* alongside that instrument's own
    news-tone score — together they satisfy the "tone score + Fear & Greed reading per
    asset" acceptance criterion. `FearGreedProvider` is always called through
    `RoutingFearGreedProvider` (see `core/di/container.py`), which never raises — any
    live-fetch failure already degrades to a fixture reading before reaching this use case.

    Never raises on a structured-output failure: downgrades to a neutral, zero-signal
    tone score instead of crashing the caller — same broad-catch shape as
    `GenerateSignal._classify_impact`. DOES raise `UnknownInstrumentError` for a symbol
    outside the curated universe — same "can't ground a per-asset read without knowing
    the asset" contract as `GenerateSignal.execute`.
    """

    def __init__(
        self,
        news_provider: NewsProvider,
        fear_greed_provider: FearGreedProvider,
        instrument_universe: InstrumentUniverse,
        llm_provider: LLMProvider,
        sentiment_repository: SentimentRepository,
        freshness_policy: FreshnessPolicy,
        retention_keep: int,
        bullish_threshold: float,
        bearish_threshold: float,
    ) -> None:
        self._news_provider = news_provider
        self._fear_greed_provider = fear_greed_provider
        self._instrument_universe = instrument_universe
        self._llm_provider = llm_provider
        self._sentiment_repository = sentiment_repository
        self._freshness_policy = freshness_policy
        self._retention_keep = retention_keep
        self._bullish_threshold = bullish_threshold
        self._bearish_threshold = bearish_threshold

    async def execute(
        self, instrument_symbol: str, locale: str, *, force: bool = False
    ) -> SentimentReading:
        """Ensure a fresh `SentimentReading` exists for `(symbol, locale)` and return it.

        Persisted and freshness-gated since issue #29. Before that, this use case recomputed
        a tone score on every single call and threw the result away — the purest recompute
        waste in the codebase, since a tone score is shared, non-personalized analysis. Now a
        reading still within its asset class's TTL is returned as-is: no LLM call, no new row.

        `force` is internal only (background refresh / manual trigger), for the same reason as
        `GenerateSignal.execute` — see that method's docstring.
        """
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        if not force:
            cached = await self._latest_reading(instrument.symbol, locale)
            if cached is not None and self._freshness_policy.is_fresh(
                cached.created_at, instrument.asset_class
            ):
                logger.info(
                    "Sentiment for %s (%s) served from cache; skipping LLM run.",
                    instrument.symbol,
                    locale,
                )
                return cached

        news_items = await self._gather_news(instrument)
        fear_greed = await self._fear_greed_provider.get_fear_greed_index()
        classification = await self._classify_tone(instrument, news_items, locale)
        tone_label = _bucket_tone_label(
            classification.tone_score, self._bullish_threshold, self._bearish_threshold
        )

        reading = SentimentReading(
            id=str(uuid.uuid4()),
            instrument_symbol=instrument.symbol,
            tone_score=classification.tone_score,
            tone_label=tone_label,
            fear_greed=fear_greed,
            evidence=[_to_evidence(item) for item in news_items],
            rationale=classification.reasoning,
            disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
            locale=locale,
        )
        return await self._persist(reading, locale)

    async def _latest_reading(self, symbol: str, locale: str) -> SentimentReading | None:
        """Cache lookup; a store blip degrades to "no cache" (recompute) rather than raising —
        same guard as `GenerateSignal._latest_signal`."""
        try:
            return await self._sentiment_repository.get_latest_for_instrument(symbol, locale)
        except Exception:
            logger.warning(
                "Sentiment cache lookup failed for %s (%s); recomputing.",
                symbol,
                locale,
                exc_info=True,
            )
            return None

    async def _persist(self, reading: SentimentReading, locale: str) -> SentimentReading:
        """Persist the reading and prune old ones, degrading to the in-memory reading if the
        store is unavailable.

        Never raises: this use case's contract has always been "degrade, don't crash the
        caller" (see the class docstring), and it is reached from a chat tool as well as a REST
        endpoint. Losing the *cache write* is strictly better than losing the answer we just
        paid an LLM call for.
        """
        try:
            persisted = await self._sentiment_repository.create(reading)
        except Exception:
            logger.warning(
                "Persisting sentiment for %s (%s) failed; returning the unsaved reading.",
                reading.instrument_symbol,
                locale,
                exc_info=True,
            )
            return reading
        try:
            await self._sentiment_repository.prune_for_instrument(
                reading.instrument_symbol, locale, self._retention_keep
            )
        except Exception:
            logger.warning(
                "Sentiment retention prune failed for %s (%s).",
                reading.instrument_symbol,
                locale,
                exc_info=True,
            )
        return persisted

    async def _gather_news(self, instrument: Instrument) -> list[NewsItem]:
        """Fetch instrument-specific news, broadening to asset-class context if there's none.

        Simpler than `GenerateSignal._gather_news`'s "≥2 distinct sources" broadening rule:
        that floor exists to satisfy HU1's acceptance criterion for a `Signal` specifically,
        and is a hard error there. A tone score has no such contract — it degrades to a
        neutral 0.0 rather than failing — so this broadens only when the direct fetch is
        completely empty, keeping the score from being computed against zero evidence when
        asset-class-level context is available. (`SentimentReading` IS persisted since issue
        #29; that changed the caching, not this sourcing rule.)
        """
        direct = await self._news_provider.fetch_news(symbols=[instrument.symbol])
        if direct:
            return direct
        return await self._news_provider.fetch_news(asset_class=instrument.asset_class)

    async def _classify_tone(
        self, instrument: Instrument, news_items: list[NewsItem], locale: str
    ) -> SentimentClassification:
        """Score the tone, writing `reasoning` in `locale`.

        The locale instruction is new with issue #29: `locale` is now part of this reading's
        cache key, so a reading stored under `es` must actually *be* in Spanish — otherwise the
        cache would serve a correctly-keyed row whose prose is in the wrong language. Same
        `build_locale_instruction` helper every other LLM-authored pipeline already uses.
        """
        try:
            raw = await self._llm_provider.complete_structured(
                messages=[
                    Message(
                        role=MessageRole.SYSTEM,
                        content=_CLASSIFICATION_SYSTEM_PROMPT + build_locale_instruction(locale),
                    ),
                    Message(
                        role=MessageRole.USER,
                        content=_format_news_context(instrument, news_items),
                    ),
                ],
                schema=SentimentClassification.model_json_schema(),
                schema_name=_CLASSIFICATION_SCHEMA_NAME,
            )
            return SentimentClassification.model_validate(raw)
        except Exception:
            # `OpenAIProvider.complete_structured` raises when no OPENAI_API_KEY is
            # configured; a malformed/unparseable response raises via `.model_validate`
            # above. Either way, caught here and downgraded to an explicit neutral score
            # instead of crashing the pipeline — same broad-catch shape as
            # `GenerateSignal._classify_impact`.
            return SentimentClassification(tone_score=0.0, reasoning=_FALLBACK_REASONING)


def _bucket_tone_label(
    tone_score: float, bullish_threshold: float, bearish_threshold: float
) -> SentimentLabel:
    """Bucket a raw `tone_score` into `SentimentLabel`, using configured thresholds.

    Thresholds come from `Settings` (`sentiment_bullish_threshold`/
    `sentiment_bearish_threshold`), never hardcoded here — same rationale as
    `bucket_volatility_regime`'s configurable VIX thresholds.
    """
    if tone_score >= bullish_threshold:
        return SentimentLabel.BULLISH
    if tone_score <= bearish_threshold:
        return SentimentLabel.BEARISH
    return SentimentLabel.NEUTRAL


def _to_evidence(item: NewsItem) -> SignalEvidence:
    return SignalEvidence(
        source=item.source, published_at=item.published_at, url=item.url, detail=item.title
    )


def _format_news_context(instrument: Instrument, news_items: list[NewsItem]) -> str:
    header = f"Instrument: {instrument.symbol} ({instrument.name}, {instrument.asset_class.value})"
    if not news_items:
        return f"{header}\n\nRecent news: (none available)"
    lines = [
        f"- [{item.published_at.isoformat()}] {item.source}: {item.title} — {item.summary}"
        for item in news_items
    ]
    return f"{header}\n\nRecent news:\n" + "\n".join(lines)
