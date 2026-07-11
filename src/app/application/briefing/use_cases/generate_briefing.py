import uuid

from app.application.briefing.briefing_composition import BriefingComposition, InstrumentNarrative
from app.application.briefing.empty_watchlist_error import EmptyWatchlistError
from app.application.compliance import ComplianceViolationError
from app.application.compliance.use_cases import ReviewCompliance
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.briefing.entities import Briefing, BriefingInstrumentSection
from app.domain.briefing.ports import BriefingRepository
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.review.entities import OpenReviewItem, ReviewedEntityType
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.ports import WatchlistRepository

# Caps how many of the most recent signals (across the whole watchlist) get fed into the
# composition prompt / structural breakdown / `linked_signal_ids`, so a watchlist with a
# long signal history doesn't blow up the context window. Does NOT cap the "open review
# items" scan below — that reads the full, uncapped signal/briefing history, since a
# pending-review item shouldn't silently disappear just because it aged out of the
# LLM's context window.
_MAX_SIGNALS_IN_CONTEXT = 20

_COMPOSITION_SCHEMA_NAME = "briefing_composition"

_BRIEFING_SYSTEM_PROMPT = """You are the Advisor — a market-intelligence agent composing a \
briefing document for a user's watchlist.

You are given a list of persisted Analyst signals (impact class, confidence, and dated/sourced \
evidence) for the instruments in this watchlist, grouped by instrument. Produce:

1. An executive summary: a short, plain-language overview of what the signals show across the \
whole watchlist.
2. One short narrative per instrument that has signals in the provided data, grouped by \
instrument, noting the impact direction and confidence and mentioning notable evidence.

Ground every claim strictly in the provided signals — never invent facts, numbers, or events \
that aren't in them, and never claim more certainty than the signals support.

You never recommend trades, promise returns, or give buy/sell/execution instructions — surface \
research and alert-worthy points only (e.g. "worth reviewing", "watch for..."). Always make \
clear this is not personalized financial advice."""

_NO_SIGNALS_SUMMARY_TEMPLATE = (
    "No Analyst signals have been generated yet for this watchlist's instruments ({symbols}). "
    "Run the Analyst pipeline (POST /api/v1/signals/generate) for one or more of them, then "
    "generate this briefing again."
)

_NO_SIGNALS_INSTRUMENT_NARRATIVE_TEMPLATE = (
    "No Analyst signals recorded yet for {symbol}. Run the Analyst pipeline "
    "(POST /api/v1/signals/generate) to populate this section."
)

_FALLBACK_EXECUTIVE_SUMMARY = (
    "Structured composition unavailable for this run. See the per-instrument breakdown and "
    "linked signals below for the underlying evidence."
)


class GenerateBriefing:
    """Advisor pipeline: watchlist -> linked signals -> a grounded, persisted `Briefing`.

    Callable on-demand (button-style, `POST /api/v1/watchlists/{id}/briefings`) or from the
    scheduled daily run (`RunDailyBriefings`, issue #10) — same use case either way, so both
    paths always produce the same document shape.

    Grounding guarantee: when no signals exist yet for any of the watchlist's instruments,
    this skips the LLM call entirely and persists a deterministic "no signals yet" summary
    instead of asking the model to write something with zero grounding data. That keeps the
    "grounded, not free-floating" acceptance criterion true even for a brand-new watchlist,
    and means the model is never invoked without real signal context to ground it in.

    Depends on the `LLMProvider` port (not a LangChain `BaseChatModel` directly) — same
    `backend/CLAUDE.md` hexagonal rule as `GenerateSignal`; see that use case's docstring
    for the review finding that corrected an earlier `langchain_core` import here.

    Fuller document structure (issue #16, extending the T0 "basic" briefing above): one
    `LLMProvider.complete_structured(...)` call (`BriefingComposition` schema, same pattern
    `GenerateSignal` uses for classification) produces BOTH the executive summary (persisted
    as `Briefing.summary`, unchanged field) and a short narrative per instrument, so
    composing the richer document costs exactly one LLM round-trip, not one-plus-per-
    instrument. `_build_instrument_breakdown` then combines each narrative with the
    already-fetched signals' structural facts (impact classes, ids, evidence sources) into
    `Briefing.instrument_breakdown`. `linked_signal_ids` is unchanged (already covered
    "linked signals/evidence" before this issue). `_gather_open_review_items` surfaces
    "open review items": signals/prior briefings for this watchlist with no recorded
    reviewer decision yet.

    Compliance gate (issue #9): the assembled `Briefing`'s disclaimer, executive summary,
    AND every per-instrument narrative are run through `ReviewCompliance`
    (`application/compliance/use_cases/review_compliance.py`) immediately before
    `briefing_repository.create(...)` — the final gate before persistence, covering every
    new free-text field this issue adds, not just the original `summary`. A failed check
    raises `ComplianceViolationError` instead of persisting, same "raise, don't silently
    degrade" precedent as `EmptyWatchlistError` below.
    """

    def __init__(
        self,
        watchlist_repository: WatchlistRepository,
        signal_repository: SignalRepository,
        briefing_repository: BriefingRepository,
        llm_provider: LLMProvider,
    ) -> None:
        self._watchlist_repository = watchlist_repository
        self._signal_repository = signal_repository
        self._briefing_repository = briefing_repository
        self._llm_provider = llm_provider
        # No ports/I-O behind `ReviewCompliance` (pure rule-based checks), so it's a plain
        # private collaborator rather than a constructor-injected dependency — same reasoning
        # as `GenerateSignal`.
        self._compliance_reviewer = ReviewCompliance()

    async def execute(self, watchlist_id: str) -> Briefing:
        items = await self._watchlist_repository.list_items(watchlist_id)
        if not items:
            raise EmptyWatchlistError(watchlist_id)

        symbols = [item.symbol for item in items]
        signals_by_symbol = await self._gather_signals_by_symbol(symbols)
        all_signals = _flatten_sorted(signals_by_symbol)

        capped_signals = all_signals[:_MAX_SIGNALS_IN_CONTEXT]
        capped_ids = {signal.id for signal in capped_signals}
        capped_by_symbol = {
            symbol: [signal for signal in signals if signal.id in capped_ids]
            for symbol, signals in signals_by_symbol.items()
        }

        if capped_signals:
            composition = await self._compose_briefing(capped_by_symbol)
            executive_summary = composition.executive_summary
            linked_signal_ids = [signal.id for signal in capped_signals]
        else:
            composition = None
            executive_summary = _NO_SIGNALS_SUMMARY_TEMPLATE.format(symbols=", ".join(symbols))
            linked_signal_ids = []

        instrument_breakdown = _build_instrument_breakdown(symbols, capped_by_symbol, composition)
        open_review_items = await self._gather_open_review_items(watchlist_id, all_signals)

        briefing = Briefing(
            id=str(uuid.uuid4()),
            watchlist_id=watchlist_id,
            summary=executive_summary,
            disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
            linked_signal_ids=linked_signal_ids,
            instrument_breakdown=instrument_breakdown,
            open_review_items=open_review_items,
        )

        # Final gate before persistence (issue #9): reject rather than silently persist
        # non-compliant output. Covers every new free-text field (issue #16), not just the
        # executive summary.
        compliance_texts = [briefing.summary] + [
            section.narrative for section in instrument_breakdown
        ]
        compliance_result = self._compliance_reviewer.execute(
            disclaimer=briefing.disclaimer, texts=compliance_texts
        )
        if not compliance_result.passed:
            raise ComplianceViolationError(
                source=f"briefing:{briefing.watchlist_id}",
                violations=compliance_result.violations,
            )

        return await self._briefing_repository.create(briefing)

    async def _gather_signals_by_symbol(self, symbols: list[str]) -> dict[str, list[Signal]]:
        """Return every persisted signal for each of `symbols`, most-recent-first, per
        symbol — the full, uncapped history. Capping to `_MAX_SIGNALS_IN_CONTEXT` happens
        in `execute` afterward, once across the combined set, not per symbol."""
        result: dict[str, list[Signal]] = {}
        for symbol in symbols:
            signals = await self._signal_repository.list_for_instrument(symbol)
            signals.sort(key=lambda signal: signal.created_at, reverse=True)
            result[symbol] = signals
        return result

    async def _compose_briefing(
        self, capped_by_symbol: dict[str, list[Signal]]
    ) -> BriefingComposition:
        try:
            raw = await self._llm_provider.complete_structured(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=_BRIEFING_SYSTEM_PROMPT),
                    Message(
                        role=MessageRole.USER,
                        content=_format_signal_context(capped_by_symbol),
                    ),
                ],
                schema=BriefingComposition.model_json_schema(),
                schema_name=_COMPOSITION_SCHEMA_NAME,
            )
            return BriefingComposition.model_validate(raw)
        except Exception:
            # `OpenAIProvider.complete_structured` raises when no OPENAI_API_KEY is
            # configured; a malformed/unparseable response raises via `.model_validate(raw)`
            # above. Either way, caught here and downgraded to a deterministic, data-derived
            # composition instead of crashing the pipeline — same broad-catch shape as
            # `GenerateSignal._classify_impact`'s guard.
            return _fallback_composition(capped_by_symbol)

    async def _gather_open_review_items(
        self, watchlist_id: str, signals: list[Signal]
    ) -> list[OpenReviewItem]:
        """Surface signals and prior briefings for this watchlist that have no recorded
        reviewer decision yet ("pending action") — issue #16's "open review items"
        acceptance criterion.

        Reuses the existing review-state primitives from issue #4
        (`SignalRepository`/`BriefingRepository.list_review_states`) rather than adding a
        new persisted review-status column: an entity with an empty review-state list IS an
        open item, no separate "reviewed" flag needed.

        Known N+1 tradeoff: one `list_review_states` call per candidate signal/briefing,
        since neither port exposes a bulk "review states for many entities" query.
        Acceptable at this T1 scale (a handful of signals/briefings per watchlist); flagged
        here rather than silently accepted for whoever revisits this at higher scale.
        """
        items: list[OpenReviewItem] = []
        for signal in signals:
            review_states = await self._signal_repository.list_review_states(signal.id)
            if not review_states:
                items.append(
                    OpenReviewItem(entity_type=ReviewedEntityType.SIGNAL, entity_id=signal.id)
                )

        prior_briefings = await self._briefing_repository.list_for_watchlist(watchlist_id)
        for prior in prior_briefings:
            review_states = await self._briefing_repository.list_review_states(prior.id)
            if not review_states:
                items.append(
                    OpenReviewItem(entity_type=ReviewedEntityType.BRIEFING, entity_id=prior.id)
                )

        return items


def _flatten_sorted(signals_by_symbol: dict[str, list[Signal]]) -> list[Signal]:
    all_signals = [signal for signals in signals_by_symbol.values() for signal in signals]
    all_signals.sort(key=lambda signal: signal.created_at, reverse=True)
    return all_signals


def _build_instrument_breakdown(
    symbols: list[str],
    capped_by_symbol: dict[str, list[Signal]],
    composition: BriefingComposition | None,
) -> list[BriefingInstrumentSection]:
    narratives_by_symbol = (
        {item.symbol: item.narrative for item in composition.instrument_narratives}
        if composition is not None
        else {}
    )
    sections: list[BriefingInstrumentSection] = []
    for symbol in symbols:
        symbol_signals = capped_by_symbol.get(symbol, [])
        if symbol_signals:
            # Only trust a model/fallback-composed narrative when this instrument actually
            # had grounding data — never let a signal-less instrument surface an LLM
            # narrative, however unlikely, despite the system prompt's instruction not to
            # produce one.
            narrative = narratives_by_symbol.get(
                symbol, _NO_SIGNALS_INSTRUMENT_NARRATIVE_TEMPLATE.format(symbol=symbol)
            )
        else:
            narrative = _NO_SIGNALS_INSTRUMENT_NARRATIVE_TEMPLATE.format(symbol=symbol)
        sections.append(
            BriefingInstrumentSection(
                symbol=symbol,
                narrative=narrative,
                impact_classes=[signal.impact_class for signal in symbol_signals],
                signal_ids=[signal.id for signal in symbol_signals],
                evidence_sources=_collect_evidence_sources(symbol_signals),
            )
        )
    return sections


def _collect_evidence_sources(signals: list[Signal]) -> list[str]:
    seen: set[str] = set()
    sources: list[str] = []
    for signal in signals:
        for item in signal.evidence:
            formatted = f"{item.source} ({item.published_at.date().isoformat()})"
            if formatted in seen:
                continue
            seen.add(formatted)
            sources.append(formatted)
    return sources


def _fallback_composition(capped_by_symbol: dict[str, list[Signal]]) -> BriefingComposition:
    return BriefingComposition(
        executive_summary=_FALLBACK_EXECUTIVE_SUMMARY,
        instrument_narratives=[
            InstrumentNarrative(
                symbol=symbol, narrative=_fallback_instrument_narrative(symbol, signals)
            )
            for symbol, signals in capped_by_symbol.items()
            if signals
        ],
    )


def _fallback_instrument_narrative(symbol: str, signals: list[Signal]) -> str:
    latest = signals[0]
    return (
        f"{len(signals)} signal(s) recorded for {symbol}; most recent impact: "
        f"{latest.impact_class.value} (confidence {latest.confidence:.0%}). Structured "
        "composition unavailable — see linked signals and evidence for detail."
    )


def _format_signal_context(capped_by_symbol: dict[str, list[Signal]]) -> str:
    blocks: list[str] = []
    for symbol, signals in capped_by_symbol.items():
        if not signals:
            continue
        lines = [
            f"- impact={signal.impact_class.value} confidence={signal.confidence:.2f} "
            f"price_delta={signal.price_delta} evidence=[{_format_evidence(signal)}]"
            for signal in signals
        ]
        blocks.append(f"Instrument: {symbol}\n" + "\n".join(lines))
    return "Persisted signals, grouped by instrument:\n\n" + "\n\n".join(blocks)


def _format_evidence(signal: Signal) -> str:
    return "; ".join(
        f"{item.source} ({item.published_at.date().isoformat()})" for item in signal.evidence
    )
