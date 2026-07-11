import uuid

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.application.signals.insufficient_evidence_error import InsufficientEvidenceError
from app.application.signals.signal_classification import SignalClassification
from app.application.signals.unknown_instrument_error import UnknownInstrumentError
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.market.entities import Instrument, NewsItem
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider, NewsProvider
from app.domain.signals.entities import ImpactClass, Signal, SignalEvidence
from app.domain.signals.ports import SignalRepository

# HU1 acceptance criterion: "≥2 news sources with source + date attached to each signal".
_MIN_DISTINCT_SOURCES = 2

_CLASSIFICATION_SYSTEM_PROMPT = """You are the Analyst — a market-intelligence agent that \
classifies how recent news impacts a single financial instrument.

Given an instrument and a list of dated, sourced news items, classify the likely impact as \
positive, negative, neutral, or uncertain, with a confidence score between 0 and 1. Ground \
your classification strictly in the provided news items — never invent facts, sources, or \
events that aren't in them. If the news is mixed, ambiguous, or too thin to call a direction, \
prefer "uncertain" with a low confidence over guessing.

This is research/informational output only — never trading instructions, and never phrased as \
personalized advice."""

_FALLBACK_REASONING = "fallback classification (structured output unavailable)"


class GenerateSignal:
    """Analyst pipeline: news -> instrument linking -> impact classification -> persisted `Signal`.

    Deliberately NOT built on the `AgentRunner` port. `AgentRunner.stream(thread_id, message)`
    is shaped for SSE chat turns (a `thread_id` plus a running conversation, yielding token/trace
    events) — that contract doesn't fit a batch pipeline that takes one instrument symbol and
    returns one persisted structured entity. Modeling this instead as a plain application-layer
    use case (constructor-injected with `NewsProvider`, `MarketDataProvider`,
    `InstrumentUniverse`, `SignalRepository`, and a LangChain `BaseChatModel` from
    `infrastructure/llm/chat_model_factory.build_chat_model`) keeps `AgentRunner`'s contract
    intact for the chat/SSE layer, follows "one port, one responsibility", and can be upgraded to
    a LangGraph subgraph later behind this same `execute(instrument_symbol)` signature without
    forcing every future batch pipeline through the streaming contract. See issue #2's design
    guidance for the full tradeoff discussion.

    News-sourcing note (the "≥2 sources" criterion above): fetches news scoped to the
    instrument's symbol first; if fewer than `_MIN_DISTINCT_SOURCES` distinct sources come back
    (common with the packaged dev fixture, which seeds ~1 article per symbol), broadens to the
    instrument's asset class as supplementary market-context evidence rather than failing
    outright. This is a documented tradeoff, not a bug: the fixture's crypto articles are all
    sourced from CoinDesk, so crypto signals generated in dev without a live `NewsProvider` API
    key configured (`MARKETAUX_API_KEY` / `NEWSAPI_API_KEY` / `FINNHUB_API_KEY`) may still ship
    with a single distinct source — configuring any one of those keys resolves it. Only a hard
    floor of >=1 real news item is enforced (`InsufficientEvidenceError` otherwise); no evidence
    is ever fabricated, and no historical-analogs evidence is fabricated either — that placeholder
    is intentionally omitted until the T1 RAG issue lands real analog data.
    """

    def __init__(
        self,
        news_provider: NewsProvider,
        market_data_provider: MarketDataProvider,
        instrument_universe: InstrumentUniverse,
        signal_repository: SignalRepository,
        model: BaseChatModel,
    ) -> None:
        self._news_provider = news_provider
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe
        self._signal_repository = signal_repository
        self._model = model

    async def execute(self, instrument_symbol: str) -> Signal:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        news_items = await self._gather_news(instrument)
        if not news_items:
            raise InsufficientEvidenceError(instrument.symbol)

        classification = await self._classify_impact(instrument, news_items)
        price_delta = await self._compute_price_delta(instrument)

        signal = Signal(
            id=str(uuid.uuid4()),
            instrument_symbol=instrument.symbol,
            impact_class=classification.impact_class,
            confidence=classification.confidence,
            evidence=[_to_evidence(item) for item in news_items],
            disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
            price_delta=price_delta,
        )
        return await self._signal_repository.create(signal)

    async def _gather_news(self, instrument: Instrument) -> list[NewsItem]:
        """Fetch instrument-specific news, broadening to asset-class context if too thin.

        See the class docstring's "News-sourcing note" for why broadening happens and its
        known dev-fixture limitation for crypto instruments.
        """
        direct = await self._news_provider.fetch_news(symbols=[instrument.symbol])
        if len({item.source for item in direct}) >= _MIN_DISTINCT_SOURCES:
            return direct

        context = await self._news_provider.fetch_news(asset_class=instrument.asset_class)
        seen_ids = {item.id for item in direct}
        return direct + [item for item in context if item.id not in seen_ids]

    async def _classify_impact(
        self, instrument: Instrument, news_items: list[NewsItem]
    ) -> SignalClassification:
        try:
            structured_model = self._model.with_structured_output(SignalClassification)
            result = await structured_model.ainvoke(
                [
                    SystemMessage(content=_CLASSIFICATION_SYSTEM_PROMPT),
                    HumanMessage(content=_format_news_context(instrument, news_items)),
                ]
            )
            if not isinstance(result, SignalClassification):
                raise TypeError(f"Unexpected structured-output result: {result!r}")
            return result
        except Exception:
            # Mirrors `supervisor_router_node.py`'s guard: the fallback fake chat model
            # (no OPENAI_API_KEY) raises NotImplementedError on `with_structured_output`,
            # caught here and downgraded to an explicit "uncertain, zero confidence" call
            # instead of crashing the pipeline.
            return SignalClassification(
                impact_class=ImpactClass.UNCERTAIN, confidence=0.0, reasoning=_FALLBACK_REASONING
            )

    async def _compute_price_delta(self, instrument: Instrument) -> float | None:
        """Percentage price change over the provider's default lookback window, or `None`."""
        try:
            series = await self._market_data_provider.get_price_series(instrument)
        except Exception:
            return None
        if len(series.candles) < 2 or series.candles[0].close == 0:
            return None
        first, last = series.candles[0], series.candles[-1]
        return round((last.close - first.close) / first.close * 100, 4)


def _to_evidence(item: NewsItem) -> SignalEvidence:
    return SignalEvidence(
        source=item.source, published_at=item.published_at, url=item.url, detail=item.title
    )


def _format_news_context(instrument: Instrument, news_items: list[NewsItem]) -> str:
    lines = [
        f"- [{item.published_at.isoformat()}] {item.source}: {item.title} — {item.summary}"
        for item in news_items
    ]
    header = f"Instrument: {instrument.symbol} ({instrument.name}, {instrument.asset_class.value})"
    return f"{header}\n\nRecent news:\n" + "\n".join(lines)
