import asyncio
import logging
import uuid

from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.common import build_locale_instruction
from app.application.compliance import ComplianceViolationError
from app.application.compliance.use_cases import ReviewCompliance
from app.application.signals.insufficient_evidence_error import InsufficientEvidenceError
from app.application.signals.signal_classification import SignalClassification
from app.application.signals.unknown_instrument_error import UnknownInstrumentError
from app.domain.agents import LLMProviderUnavailableError
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.freshness import FreshnessPolicy
from app.domain.market.entities import Instrument, NewsItem
from app.domain.market.ports import InstrumentUniverse, MarketDataProvider, NewsProvider
from app.domain.signals.entities import ImpactClass, Signal, SignalEvidence
from app.domain.signals.ports import SignalRepository

logger = logging.getLogger(__name__)

_CLASSIFICATION_SCHEMA_NAME = "signal_classification"

_CLASSIFICATION_SYSTEM_PROMPT = """You are the Analyst — a market-intelligence agent that \
classifies how recent news impacts a single financial instrument.

Given an instrument, its recent price move, any historical analogs, and a list of dated, \
sourced news items, produce:
- impact_class: positive, negative, neutral, or uncertain;
- confidence: a score between 0 and 1;
- reasoning: one or two sentences grounding the call in the evidence;
- thesis: a 3-5 sentence analytical thesis explaining what the evidence implies for the \
instrument's outlook and why;
- key_drivers: the concrete factors from the evidence driving the call;
- risk_factors: what would invalidate the call — the main risks or counterpoints.

Ground everything strictly in the provided news items, price context, and historical \
analogs — never invent facts, sources, or events that aren't in them. If the news is mixed, \
ambiguous, or too thin to call a direction, prefer "uncertain" with a low confidence over \
guessing.

This is research/informational output only — never trading instructions, and never phrased as \
personalized advice."""

_FALLBACK_REASONING = "fallback classification (structured output unavailable)"
_FALLBACK_THESIS = (
    "Automated analysis is unavailable for this signal (the classification model could not "
    "be reached). No thesis was generated; treat this as an unclassified alert only."
)


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

    News-sourcing note (HU1 acceptance criterion: "≥2 news sources with source + date attached
    to each signal", configured via `Settings.min_distinct_news_sources` and injected here as
    `min_distinct_sources`): fetches news scoped to the instrument's symbol first; if fewer than
    `self._min_distinct_sources` distinct sources come back, broadens to the instrument's asset
    class as supplementary market-context evidence rather than failing outright. The
    distinct-source count is re-checked after broadening (issue #25):
    a hard floor of >=1 real news item AND >=`self._min_distinct_sources` distinct sources is
    enforced — `InsufficientEvidenceError` is raised for either shortfall, before classification
    or persistence — so a signal can never ship with fewer than 2 distinct sources, even in dev.
    The packaged fixture (`infrastructure/seeds/news_fixture.json`) seeds >=2 distinct sources
    per asset class (including crypto and forex, each with only one instrument's worth of
    direct-symbol coverage) precisely so this floor doesn't make every fixture-only signal
    generation call fail without a live `NewsProvider` API key configured
    (`MARKETAUX_API_KEY` / `NEWSAPI_API_KEY` / `FINNHUB_API_KEY`). No news evidence is ever
    fabricated to satisfy the floor. Historical-analog evidence (issue #15) is retrieved via
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
        min_distinct_sources: int,
        freshness_policy: FreshnessPolicy,
        retention_keep: int,
        retry_max_attempts: int = 2,
        retry_backoff_base_seconds: float = 0.5,
    ) -> None:
        self._news_provider = news_provider
        self._market_data_provider = market_data_provider
        self._instrument_universe = instrument_universe
        self._signal_repository = signal_repository
        self._llm_provider = llm_provider
        self._find_historical_analogs = find_historical_analogs
        self._index_signal_analog = index_signal_analog
        self._min_distinct_sources = min_distinct_sources
        # Freshness cache + retention (issue #29). Both come from `Settings` via the DI
        # container — no TTL or retention count is hardcoded here.
        self._freshness_policy = freshness_policy
        self._retention_keep = retention_keep
        # Bounded retry around the transient-failure path of `_classify_impact` before it
        # degrades to the honest fallback (issue #55). Defaults mirror `Settings`' own
        # defaults so a caller that doesn't wire them (e.g. the batch pipeline) still
        # retries — same constructor-default pattern as `SupabaseSignalRepository`.
        self._retry_max_attempts = retry_max_attempts
        self._retry_backoff_base_seconds = retry_backoff_base_seconds
        # No ports/I-O behind `ReviewCompliance` (pure rule-based checks), so it's a plain
        # private collaborator rather than a constructor-injected dependency — nothing to
        # swap, and routers don't need to resolve/pass it via `Depends`.
        self._compliance_reviewer = ReviewCompliance()

    async def execute(self, instrument_symbol: str, locale: str, *, force: bool = False) -> Signal:
        """Ensure a fresh `Signal` exists for `(instrument_symbol, locale)` and return it.

        Freshness-gated since issue #29: a `Signal` is shared, non-personalized analysis, so
        N users asking about AAPL within the TTL window should cost ONE LLM run, not N. Unless
        `force`, a cached signal that is still within its asset class's TTL is returned as-is —
        no LLM call, no new row.

        `force` is INTERNAL ONLY. It is for the background refresh job and for
        `ForceAnalyzeNewsItem` (the manual "Analizar ahora" button, which must genuinely
        re-analyze or the button looks broken). It is deliberately NOT exposed as a query
        param on the public `POST /api/v1/signals/generate` — a client that can set
        `force=true` can trivially bust the cache and reintroduce the exact cost this gate
        exists to remove. The public endpoint's contract is now "ensure fresh", not "always
        recompute".
        """
        instrument = self._instrument_universe.by_symbol(instrument_symbol)
        if instrument is None:
            raise UnknownInstrumentError(instrument_symbol)

        # Fetched even under `force`, because it also backs the degraded-write guard below.
        cached = await self._latest_signal(instrument.symbol, locale)
        if not force and cached is not None and self._is_reusable(cached, instrument):
            logger.info(
                "Signal for %s (%s) served from cache (created_at=%s); skipping LLM run.",
                instrument.symbol,
                locale,
                cached.created_at.isoformat(),
            )
            return cached

        news_items = await self._gather_news(instrument)
        if not news_items:
            raise InsufficientEvidenceError(instrument.symbol)

        # Hard floor (issue #25): `_gather_news` broadens to asset-class context when the
        # direct search is too thin, but never re-checked the count afterward — a signal
        # could still ship with a single distinct source. Re-verify post-broadening, before
        # any classification or persistence work happens, per HU1's "≥2 news sources"
        # acceptance criterion.
        distinct_sources = len({item.source for item in news_items})
        if distinct_sources < self._min_distinct_sources:
            raise InsufficientEvidenceError(instrument.symbol, distinct_sources)

        # Gather quantitative + historical context BEFORE classification (issue #40) so the
        # model can actually reason over it. `price_delta` is independent of the impact
        # class. Historical-analog retrieval (issue #15) is done here too — up to N
        # semantically similar past signals, attached as `[análogo histórico]`-tagged
        # evidence and fed into the prompt. Since the real impact class isn't known yet,
        # the retrieval query uses a neutral `UNCERTAIN` placeholder; the event summary is
        # what drives the semantic match. Neither call blocks or fails signal generation —
        # see `_compute_price_delta` / `FindHistoricalAnalogs.execute`'s guards.
        price_delta = await self._compute_price_delta(instrument)
        analog_summary = news_items[0].title
        analogs = await self._find_historical_analogs.execute(
            instrument.symbol, ImpactClass.UNCERTAIN, analog_summary
        )

        classification, analysis_available = await self._classify_impact(
            instrument, news_items, price_delta, analogs, locale
        )

        evidence = [_to_evidence(item) for item in news_items] + analogs

        # Degraded-write guard (issue #29): if classification fell back (no LLM key, exhausted
        # retries) but a real analysis already exists for this key, do NOT persist the empty
        # one. It would become `latest` and hide the last good thesis behind an "análisis no
        # disponible" card — a strictly worse answer than the one we already have. Applies even
        # under `force`: forcing means "try to refresh", never "overwrite good with garbage".
        if not analysis_available and cached is not None and cached.analysis_available:
            logger.warning(
                "Signal classification for %s (%s) degraded; keeping the last good analysis "
                "(created_at=%s) rather than persisting an empty one.",
                instrument.symbol,
                locale,
                cached.created_at.isoformat(),
            )
            return cached

        signal = Signal(
            id=str(uuid.uuid4()),
            instrument_symbol=instrument.symbol,
            impact_class=classification.impact_class,
            confidence=classification.confidence,
            locale=locale,
            thesis=classification.thesis,
            key_drivers=classification.key_drivers,
            risk_factors=classification.risk_factors,
            analysis_available=analysis_available,
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

        await self._prune(instrument.symbol, locale)

        return persisted

    async def _latest_signal(self, symbol: str, locale: str) -> Signal | None:
        """The newest persisted signal for this cache key, or `None`.

        A cache lookup must never be the reason a generation fails: a store blip degrades to
        "no cache" (recompute) rather than raising, which is the pre-#29 behavior anyway.
        """
        try:
            return await self._signal_repository.get_latest_for_instrument(symbol, locale)
        except Exception:
            logger.warning(
                "Cache lookup failed for %s (%s); regenerating.", symbol, locale, exc_info=True
            )
            return None

    def _is_reusable(self, signal: Signal, instrument: Instrument) -> bool:
        """Whether a cached signal can be served instead of running the pipeline.

        Fresh AND a real analysis. The `analysis_available` half matters: a degraded row
        (persisted before this guard existed, or written when no good row existed to fall back
        on) must not pin the cache for a whole TTL window — otherwise a single LLM outage
        would suppress every retry until it expired.
        """
        return signal.analysis_available and self._freshness_policy.is_fresh(
            signal.created_at, instrument.asset_class
        )

    async def _prune(self, symbol: str, locale: str) -> None:
        """Trim this cache key's history to the configured retention (issue #29).

        Best-effort and post-persistence: retention is housekeeping, and failing the caller's
        request because cleanup of OLD rows failed would trade a real answer for a tidy table.
        """
        try:
            deleted = await self._signal_repository.prune_for_instrument(
                symbol, locale, self._retention_keep
            )
        except Exception:
            logger.warning("Signal retention prune failed for %s (%s).", symbol, locale, exc_info=True)
            return
        if deleted:
            logger.info("Pruned %d stale signal(s) for %s (%s).", deleted, symbol, locale)

    async def _gather_news(self, instrument: Instrument) -> list[NewsItem]:
        """Fetch instrument-specific news, broadening to asset-class context if too thin.

        See the class docstring's "News-sourcing note" for why broadening happens and its
        known dev-fixture limitation for crypto instruments.
        """
        direct = await self._news_provider.fetch_news(symbols=[instrument.symbol])
        if len({item.source for item in direct}) >= self._min_distinct_sources:
            return direct

        context = await self._news_provider.fetch_news(asset_class=instrument.asset_class)
        seen_ids = {item.id for item in direct}
        return direct + [item for item in context if item.id not in seen_ids]

    async def _classify_impact(
        self,
        instrument: Instrument,
        news_items: list[NewsItem],
        price_delta: float | None,
        analogs: list[SignalEvidence],
        locale: str,
    ) -> tuple[SignalClassification, bool]:
        """Classify impact, returning `(classification, analysis_available)`.

        `analysis_available` is `False` only on the fallback path below (no LLM backend /
        exhausted retries on a transient failure), so the caller can persist a marker
        distinguishing a real analysis from a degraded, empty one. The fallback always
        returns `impact_class=UNCERTAIN, confidence=0.0`, so a degraded signal can never
        show a confident directional badge alongside an unavailable analysis (issue #55).

        The blanket `except Exception` this replaced (issue #55) swallowed the root cause
        without a trace: a missing `OPENAI_API_KEY`, a rate-limit, a timeout, and an
        unparseable structured response all collapsed into the same silent "uncertain"
        result. Now every failure is logged with its provider error class + message, and
        transient failures are retried with exponential backoff before degrading. A
        permanently-unavailable backend (`LLMProviderUnavailableError`, e.g. no API key)
        is logged once and degraded immediately — retrying it can't help.
        """
        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content=_CLASSIFICATION_SYSTEM_PROMPT + build_locale_instruction(locale),
            ),
            Message(
                role=MessageRole.USER,
                content=_format_news_context(instrument, news_items, price_delta, analogs),
            ),
        ]
        attempt = 0
        while True:
            try:
                raw = await self._llm_provider.complete_structured(
                    messages=messages,
                    schema=SignalClassification.model_json_schema(),
                    schema_name=_CLASSIFICATION_SCHEMA_NAME,
                )
                return SignalClassification.model_validate(raw), True
            except LLMProviderUnavailableError as exc:
                logger.warning(
                    "Signal classification for %s degraded to fallback: LLM provider "
                    "unavailable (%s: %s). Not retrying — this needs configuration, not a retry.",
                    instrument.symbol,
                    type(exc).__name__,
                    exc,
                )
                return _build_fallback_classification(), False
            except Exception as exc:
                # Transient: rate limit / timeout / malformed or unparseable structured
                # output (`json.loads` in the adapter, or `.model_validate(raw)` above).
                attempt += 1
                if attempt > self._retry_max_attempts:
                    logger.error(
                        "Signal classification for %s exhausted %d retr(y/ies); degrading "
                        "to fallback. Last error (%s: %s)",
                        instrument.symbol,
                        self._retry_max_attempts,
                        type(exc).__name__,
                        exc,
                    )
                    return _build_fallback_classification(), False
                delay = self._retry_backoff_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Signal classification for %s failed (attempt %d/%d, %s: %s); "
                    "retrying in %.2fs",
                    instrument.symbol,
                    attempt,
                    self._retry_max_attempts,
                    type(exc).__name__,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

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


def _build_fallback_classification() -> SignalClassification:
    """The honest degraded classification used when the Analyst can't classify (issue #55).

    Always `UNCERTAIN` with `confidence=0.0` and an empty thesis, so a signal persisted
    from this path (`analysis_available=False`) can never contradict itself by showing a
    confident directional badge next to an "análisis no disponible" message.
    """
    return SignalClassification(
        impact_class=ImpactClass.UNCERTAIN,
        confidence=0.0,
        reasoning=_FALLBACK_REASONING,
        thesis=_FALLBACK_THESIS,
    )


def _to_evidence(item: NewsItem) -> SignalEvidence:
    return SignalEvidence(
        source=item.source, published_at=item.published_at, url=item.url, detail=item.title
    )


def _format_news_context(
    instrument: Instrument,
    news_items: list[NewsItem],
    price_delta: float | None,
    analogs: list[SignalEvidence],
) -> str:
    header = f"Instrument: {instrument.symbol} ({instrument.name}, {instrument.asset_class.value})"
    price_line = (
        f"Recent price move: {price_delta:+.2f}% over the provider's lookback window."
        if price_delta is not None
        else "Recent price move: unavailable."
    )
    news_lines = [
        f"- [{item.published_at.isoformat()}] {item.source}: {item.title} — {item.summary}"
        for item in news_items
    ]
    sections = [header, "", price_line, "", "Recent news:", *news_lines]
    if analogs:
        analog_lines = [f"- {analog.detail}" for analog in analogs if analog.detail]
        if analog_lines:
            sections += ["", "Historical analogs:", *analog_lines]
    return "\n".join(sections)
