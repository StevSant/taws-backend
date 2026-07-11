import uuid

from app.application.sentiment.sentiment_classification import SentimentClassification
from app.application.sentiment.unknown_instrument_error import UnknownInstrumentError
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.market.entities import Instrument, NewsItem
from app.domain.market.ports import InstrumentUniverse, NewsProvider
from app.domain.sentiment.entities import SentimentLabel, SentimentReading
from app.domain.sentiment.ports import FearGreedProvider
from app.domain.signals.entities import SignalEvidence

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
        bullish_threshold: float,
        bearish_threshold: float,
    ) -> None:
        self._news_provider = news_provider
        self._fear_greed_provider = fear_greed_provider
        self._instrument_universe = instrument_universe
        self._llm_provider = llm_provider
        self._bullish_threshold = bullish_threshold
        self._bearish_threshold = bearish_threshold

    async def execute(self, instrument_symbol: str) -> SentimentReading:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        news_items = await self._gather_news(instrument)
        fear_greed = await self._fear_greed_provider.get_fear_greed_index()
        classification = await self._classify_tone(instrument, news_items)
        tone_label = _bucket_tone_label(
            classification.tone_score, self._bullish_threshold, self._bearish_threshold
        )

        return SentimentReading(
            id=str(uuid.uuid4()),
            instrument_symbol=instrument.symbol,
            tone_score=classification.tone_score,
            tone_label=tone_label,
            fear_greed=fear_greed,
            evidence=[_to_evidence(item) for item in news_items],
            rationale=classification.reasoning,
            disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
        )

    async def _gather_news(self, instrument: Instrument) -> list[NewsItem]:
        """Fetch instrument-specific news, broadening to asset-class context if there's none.

        Simpler than `GenerateSignal._gather_news`'s "≥2 distinct sources" broadening rule
        (that rule exists to satisfy a *persisted Signal's* HU1 acceptance criterion; a
        `SentimentReading` is never persisted) — broadens only when the direct fetch is
        completely empty, so the tone score is never computed from zero evidence when
        asset-class-level context is available.
        """
        direct = await self._news_provider.fetch_news(symbols=[instrument.symbol])
        if direct:
            return direct
        return await self._news_provider.fetch_news(asset_class=instrument.asset_class)

    async def _classify_tone(
        self, instrument: Instrument, news_items: list[NewsItem]
    ) -> SentimentClassification:
        try:
            raw = await self._llm_provider.complete_structured(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=_CLASSIFICATION_SYSTEM_PROMPT),
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
