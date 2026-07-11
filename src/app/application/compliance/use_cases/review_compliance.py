import re
from collections.abc import Iterable

from app.domain.compliance.entities import ComplianceCheckResult, ComplianceViolation

_RULE_DISCLAIMER_MISSING = "disclaimer_missing"
_RULE_BANNED_PHRASE = "banned_phrase"

# Compliance ruleset, not environment config — a fixed list of phrases that would turn
# research/informational output into a promised return or an execution instruction. This is
# a domain-shaped constant (like `NOT_PERSONALIZED_ADVICE_DISCLAIMER`), not a `Settings`
# field: it never varies per environment or deployment.
#
# `\b...\b` word-boundary wrapping avoids incidental substring hits (e.g. "buy now" must not
# match inside an unrelated word like "buy nowhere").
_BANNED_PHRASES = (
    # Promised/guaranteed returns.
    "guaranteed return",
    "guaranteed returns",
    "guarantee a return",
    "guaranteed profit",
    "guaranteed profits",
    "risk-free return",
    "risk-free profit",
    "certain profit",
    "will definitely",
    # Execution / trade instructions (this product is alert/task records only — see
    # `backend/CLAUDE.md`'s "never add trading/execution columns" migration rule).
    "buy now",
    "sell now",
    "you should buy",
    "you should sell",
    "you should purchase",
    "place an order",
    "place a trade",
    "execute this trade",
    "execute the trade",
)

_BANNED_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE) for phrase in _BANNED_PHRASES
)


class ReviewCompliance:
    """Risk & Compliance Reviewer (agent fleet #6, T1): a deterministic, rule-based review
    pass over another agent's structured output, run as the final gate before persistence.

    Deliberately NOT an `AgentRunner`/LangGraph node and NOT wired into `SupervisorRoute` —
    this is a review/validation pass other pipelines call, not a chat specialist a user
    routes to. See issue #9's architecture guidance for the full rationale.

    Deliberately rule-based (regex/string matching), not an LLM judging its own kind of
    output. Two checks, both deterministic and auditable:

    1. **Disclaimer present** — `disclaimer` is a structural field on `Signal`/`Briefing`
       (`domain/signals/entities/signal.py`, `domain/briefing/entities/briefing.py`), always
       set to `NOT_PERSONALIZED_ADVICE_DISCLAIMER` by the caller, so this is a simple
       non-null/non-empty check, not free-text parsing.
    2. **No banned phrases** — a fixed regex scan (`_BANNED_PHRASE_PATTERNS`) over the
       candidate's free-text fields (e.g. an Analyst classification's `reasoning`, an
       Advisor briefing's `summary`) for promised/guaranteed-return language and
       execution/trade instructions.

    No constructor dependencies (no ports, no LLM call, no I/O) — callers may instantiate a
    fresh one per use or hold a shared instance; both are safe since this class carries no
    state and does no I/O.

    Reusable by future callers: this use case takes plain `disclaimer`/`texts` arguments, not
    a `Signal` or `Briefing` directly, specifically so the future Scenario Simulation graph's
    step 6 "Compliance" node (issue #12, not yet built as of this change — see the Scenario
    graph in the T1 architecture design) can call `execute(...)` the same way once it exists,
    without this use case needing to know about a `ScenarioResult` entity ahead of time.
    """

    def execute(
        self, *, disclaimer: str | None, texts: Iterable[str | None]
    ) -> ComplianceCheckResult:
        violations: list[ComplianceViolation] = []

        if disclaimer is None or not disclaimer.strip():
            violations.append(
                ComplianceViolation(
                    rule=_RULE_DISCLAIMER_MISSING,
                    detail="Output is missing the required not-personalized-advice disclaimer.",
                )
            )

        combined_text = " ".join(text for text in texts if text)
        seen_phrases: set[str] = set()
        for pattern in _BANNED_PHRASE_PATTERNS:
            match = pattern.search(combined_text)
            if match is None:
                continue
            matched_phrase = match.group(0).lower()
            if matched_phrase in seen_phrases:
                continue
            seen_phrases.add(matched_phrase)
            violations.append(
                ComplianceViolation(
                    rule=_RULE_BANNED_PHRASE,
                    detail=f"Output contains banned phrase: {match.group(0)!r}",
                )
            )

        return ComplianceCheckResult(passed=not violations, violations=violations)
