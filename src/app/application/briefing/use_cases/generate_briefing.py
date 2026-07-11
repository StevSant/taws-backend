import uuid

from app.application.briefing.empty_watchlist_error import EmptyWatchlistError
from app.application.compliance import ComplianceViolationError
from app.application.compliance.use_cases import ReviewCompliance
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingRepository
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.ports import WatchlistRepository

# Caps how many of the most recent signals get fed into the composition prompt, so a
# watchlist with a long signal history doesn't blow up the context window.
_MAX_SIGNALS_IN_CONTEXT = 20

_BRIEFING_SYSTEM_PROMPT = """You are the Advisor — a market-intelligence agent composing a \
short briefing for a user's watchlist.

You are given a list of persisted Analyst signals (impact class, confidence, and dated/sourced \
evidence) for the instruments in this watchlist. Summarize what they show in plain language: \
group by instrument, note the impact direction and confidence, and mention notable evidence. \
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


class GenerateBriefing:
    """Advisor pipeline: watchlist -> linked signals -> a grounded, persisted `Briefing`.

    On-demand (button-style) only — scheduling a recurring briefing is a separate T1 issue.

    Grounding guarantee: when no signals exist yet for any of the watchlist's instruments,
    this skips the LLM call entirely and persists a deterministic "no signals yet" summary
    instead of asking the model to write something with zero grounding data. That keeps the
    "grounded, not free-floating" acceptance criterion true even for a brand-new watchlist,
    and means the model is never invoked without real signal context to ground it in.

    Depends on the `LLMProvider` port (not a LangChain `BaseChatModel` directly) — same
    `backend/CLAUDE.md` hexagonal rule as `GenerateSignal`; see that use case's docstring
    for the review finding that corrected an earlier `langchain_core` import here.

    Compliance gate (issue #9): the assembled `Briefing` (disclaimer + summary) is run
    through `ReviewCompliance` (`application/compliance/use_cases/review_compliance.py`)
    immediately before `briefing_repository.create(...)` — the final gate before persistence.
    A failed check raises `ComplianceViolationError` instead of persisting, same "raise,
    don't silently degrade" precedent as `EmptyWatchlistError` below.
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
        signals = await self._gather_signals(symbols)

        if signals:
            summary = await self._compose_summary(signals)
            linked_signal_ids = [signal.id for signal in signals]
        else:
            summary = _NO_SIGNALS_SUMMARY_TEMPLATE.format(symbols=", ".join(symbols))
            linked_signal_ids = []

        briefing = Briefing(
            id=str(uuid.uuid4()),
            watchlist_id=watchlist_id,
            summary=summary,
            disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
            linked_signal_ids=linked_signal_ids,
        )

        # Final gate before persistence (issue #9): reject rather than silently persist
        # non-compliant output.
        compliance_result = self._compliance_reviewer.execute(
            disclaimer=briefing.disclaimer, texts=[briefing.summary]
        )
        if not compliance_result.passed:
            raise ComplianceViolationError(
                source=f"briefing:{briefing.watchlist_id}",
                violations=compliance_result.violations,
            )

        return await self._briefing_repository.create(briefing)

    async def _gather_signals(self, symbols: list[str]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol in symbols:
            signals.extend(await self._signal_repository.list_for_instrument(symbol))
        signals.sort(key=lambda signal: signal.created_at, reverse=True)
        return signals[:_MAX_SIGNALS_IN_CONTEXT]

    async def _compose_summary(self, signals: list[Signal]) -> str:
        return await self._llm_provider.complete(
            [
                Message(role=MessageRole.SYSTEM, content=_BRIEFING_SYSTEM_PROMPT),
                Message(role=MessageRole.USER, content=_format_signal_context(signals)),
            ]
        )


def _format_signal_context(signals: list[Signal]) -> str:
    lines = [
        f"- {signal.instrument_symbol}: impact={signal.impact_class.value} "
        f"confidence={signal.confidence:.2f} price_delta={signal.price_delta} "
        f"evidence=[{_format_evidence(signal)}]"
        for signal in signals
    ]
    return "Persisted signals:\n" + "\n".join(lines)


def _format_evidence(signal: Signal) -> str:
    return "; ".join(
        f"{item.source} ({item.published_at.date().isoformat()})" for item in signal.evidence
    )
