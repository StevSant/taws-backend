import uuid

from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.common import build_locale_instruction
from app.application.compliance import ComplianceViolationError
from app.application.compliance.use_cases import ReviewCompliance
from app.application.signals.insufficient_evidence_error import InsufficientEvidenceError
from app.application.signals.signal_classification import SignalClassification
from app.application.signals.unknown_instrument_error import UnknownInstrumentError
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.market.entities import Instrument, NewsItem
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider, NewsProvider
from app.domain.signals.entities import ImpactClass, Signal, SignalEvidence
from app.domain.signals.ports import SignalRepository

_CLASSIFICATION_SCHEMA_NAME = "signal_classification"

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
    `InstrumentUniverse`, `SignalRepository`, and the `LLMProvider` port) keeps `AgentRunner`'s
    contract intact for the chat/SSE layer, follows "one port, one responsibility", and can be
    upgraded to a LangGraph subgraph later behind this same `execute(instrument_symbol)`
    signature without forcing every future batch pipeline through the streaming contract. See
    issue #2's design guidance for the full tradeoff discussion.

    Uses `LLMProvider.complete_structured(...)` (not a LangChain `BaseChatModel` directly) for
    the classification call, per `backend/CLAUDE.md`'s hexagonal rule that `application/` never
    imports a vendor/framework package directly — an earlier version of this use case imported
    `langchain_core` here, which review correctly flagged as a hexagonal violation; `LLMProvider`
    is the existing port built for exactly this ("anything calling the LLMProvider port directly,
    not via the agent graph" — see `infrastructure/llm/openai_provider.py`'s
    `complete_structured`).

    Compliance gate (issue #9): the assembled `Signal` and the classification's `reasoning`
    text are run through `ReviewCompliance` (`application/compliance/use_cases/
    review_compliance.py`) immediately before `signal_repository.create(...)` — the final gate
    before persistence. A failed check raises `ComplianceViolationError` instead of persisting,
    following the exact same "raise, don't silently degrade" precedent as
    `InsufficientEvidenceError` below.

    News-sourcing note (the "≥2 sources" criterion above): fetches news scoped to the
    instrument's symbol first; if fewer than `_MIN_DISTINCT_SOURCES` distinct sources come back
    (common with the packaged dev fixture, which seeds ~1 article per symbol), broadens to the
    instrument's asset class as supplementary market-context evidence rather than failing
    outright. The distinct-source count is re-checked after broadening (issue #25): a hard floor
    of >=1 real news item AND >=`_MIN_DISTINCT_SOURCES` distinct sources is enforced —
    `InsufficientEvidenceError` is raised for either shortfall, before classification or
    persistence — so a signal can never ship with fewer than 2 distinct sources, even in dev. In
    practice this means crypto signals generated in dev without a live `NewsProvider` API key
    configured (`MARKETAUX_API_KEY` / `NEWSAPI_API_KEY` / `FINNHUB_API_KEY`) will fail to
    generate rather than ship under-sourced, since the packaged fixture's crypto articles are all
    sourced from CoinDesk — configuring any one of those keys resolves it. No news evidence is
    ever fabricated to satisfy the floor. Historical-analog evidence (issue #15) is retrieved via
    `FindHistoricalAnalogs` below, and is likewise never fabricated — it degrades to "no
    analogs" rather than inventing a match; see that class's docstring.
    """

    def __init__(
        self,
        news_provider: NewsProvider,
        market_data_provider: MarketDataProvider,
        instrument_universe: InstrumentUniverse,
        signal_repository: SignalRepository,
        llm_provider: LLMProvider,
        find_historical_analogs: FindHistoricalAnalogs,
        index_signal_analog: IndexSignalAnalog,
    ) -> None:
        self._news_provider = news_provider
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe
        self._signal_repository = signal_repository
        self._llm_provider = llm_provider
        self._find_historical_analogs = find_historical_analogs
        self._index_signal_analog = index_signal_analog
        # No ports/I-O behind `ReviewCompliance` (pure rule-based checks), so it's a plain
        # private collaborator rather than a constructor-injected dependency — nothing to
        # swap, and routers don't need to resolve/pass it via `Depends`.
        self._compliance_reviewer = ReviewCompliance()

    async def execute(self, instrument_symbol: str, locale: str) -> Signal:
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        news_items = await self._gather_news(instrument)
        if not news_items:
            raise InsufficientEvidenceError(instrument.symbol)

        # Hard floor (issue #25): `_gather_news` broadens to asset-class context when the
        # direct search is too thin, but never re-checked the count afterward — a signal
        # could still ship with a single distinct source. Re-verify post-broadening, before
        # any classification or persistence work happens, per HU1's "≥2 news sources"
        # acceptance criterion.
        distinct_sources = len({item.source for item in news_items})
        if distinct_sources < _MIN_DISTINCT_SOURCES:
            raise InsufficientEvidenceError(instrument.symbol, distinct_sources)

        classification = await self._classify_impact(instrument, news_items, locale)
        price_delta = await self._compute_price_delta(instrument)
        evidence = [_to_evidence(item) for item in news_items]

        # --- Historical analogs RAG (issue #15) ---------------------------------------
        # Retrieve up to N semantically similar past signals and attach them as
        # `[análogo histórico]`-tagged evidence before finalizing the signal. Never blocks
        # or fails signal generation — see `FindHistoricalAnalogs.execute`'s guard.
        analog_summary = news_items[0].title
        evidence += await self._find_historical_analogs.execute(
            instrument.symbol, classification.impact_class, analog_summary
        )
        # --------------------------------------------------------------------------------

        signal = Signal(
            id=str(uuid.uuid4()),
            instrument_symbol=instrument.symbol,
            impact_class=classification.impact_class,
            confidence=classification.confidence,
            evidence=evidence,
            disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
            price_delta=price_delta,
        )

        # Final gate before persistence (issue #9): reject rather than silently persist
        # non-compliant output. `classification.reasoning` is included even though it isn't
        # a persisted `Signal` field, since it's the Analyst's actual free-text output and
        # the only place execution/return-promise language could leak in from this pipeline.
        compliance_result = self._compliance_reviewer.execute(
            disclaimer=signal.disclaimer, texts=[classification.reasoning]
        )
        if not compliance_result.passed:
            raise ComplianceViolationError(
                source=f"signal:{signal.instrument_symbol}",
                violations=compliance_result.violations,
            )

        persisted = await self._signal_repository.create(signal)

        # Index this signal as a future historical analog (issue #15) — best-effort side
        # effect run after persistence, so a RAG-indexing failure never loses the signal.
        await self._index_signal_analog.execute(persisted, analog_summary)

        return persisted

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
        self, instrument: Instrument, news_items: list[NewsItem], locale: str
    ) -> SignalClassification:
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
                schema=SignalClassification.model_json_schema(),
                schema_name=_CLASSIFICATION_SCHEMA_NAME,
            )
            return SignalClassification.model_validate(raw)
        except Exception:
            # `OpenAIProvider.complete_structured` raises when no OPENAI_API_KEY is
            # configured (see its docstring); a malformed/unparseable response raises
            # via `.model_validate(raw)` above. Either way, caught here and downgraded
            # to an explicit "uncertain, zero confidence" call instead of crashing the
            # pipeline — same broad-catch shape as `supervisor_router_node.py`'s guard.
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
