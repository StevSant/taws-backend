import re
from collections.abc import Iterable

from app.domain.compliance.entities import ComplianceCheckResult, ComplianceViolation

_RULE_DISCLAIMER_MISSING = "disclaimer_missing"
_RULE_BANNED_PHRASE = "banned_phrase"

# Compliance ruleset, not environment config — a fixed set of *proximity* patterns that would
# turn research/informational output into a promised return or an execution instruction. This
# is a domain-shaped constant (like `NOT_PERSONALIZED_ADVICE_DISCLAIMER`), not a `Settings`
# field: it never varies per environment or deployment.
#
# Deliberately proximity-based (word A within N characters of word B, either order) rather than
# exact contiguous phrases. Exact-phrase matching (e.g. `"guaranteed return"`,
# `"you should buy"`) was found to both miss real violations phrased naturally — "we guarantee
# investors will see strong returns", "buy the dip now", one adverb breaking "you should
# [definitely] buy" — and to over-trigger on unrelated confident language (a standalone "will
# definitely" pattern flagged *any* confident statement, not just overpromised returns). See
# issue #9 review follow-up. `\b...\b` word-boundary wrapping still avoids incidental substring
# hits (e.g. "certain" must not match inside "uncertain").
_BANNED_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Promised/guaranteed returns: "guarantee" (or "guarantees"/"guaranteed") occurring near
    # "return(s)"/"profit(s)"/"gain(s)"/"upside", in either order, within a window generous
    # enough to cover natural phrasing like "we guarantee investors will see strong returns"
    # (27 chars between the two words) without also matching on totally unrelated sentences.
    re.compile(r"\bguarantee[sd]?\b.{0,40}?\b(return|profit|gain|upside)s?\b", re.IGNORECASE),
    re.compile(r"\b(return|profit|gain|upside)s?\b.{0,40}?\bguarantee[sd]?\b", re.IGNORECASE),
    re.compile(r"\brisk-free\b.{0,20}?\b(return|profit)s?\b", re.IGNORECASE),
    re.compile(r"\bcertain\b.{0,20}?\bprofit\b", re.IGNORECASE),
    # Buy/sell execution instructions: "buy"/"sell" occurring near recommendation-shaped
    # language ("should", "must", "recommend", "advise", "now", "immediately", "today"), in
    # either order. This catches imperative ("buy now"), third-person ("investors should buy"),
    # and adverb-interrupted second-person ("you should definitely buy") forms alike — the
    # deciding signal is the trade verb plus recommendation language nearby, not a fixed
    # contiguous phrase or a fixed grammatical subject.
    re.compile(
        r"\b(buy|sell)\b.{0,30}?\b(should|must|recommend|advise|now|immediately|today)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(should|must|recommend|advise)\b.{0,30}?\b(buy|sell)\b",
        re.IGNORECASE,
    ),
    # Purchase execution instructions: "purchase" scoped to co-occur with a security/trade
    # object (stock, share, position, security, equity, ticker, ...) nearby, in either order.
    # Deliberately narrower than the buy/sell patterns above — "purchase" alone paired with
    # generic nouns ("purchase insurance-like hedges", "purchase protection") is legitimate
    # hedging/research language, not an execution instruction, and must not be flagged.
    re.compile(
        r"\bpurchase\b.{0,40}?\b(stock|share|shares|position|security|equity|equities|ticker)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(stock|share|shares|position|security|equity|equities|ticker)\b.{0,40}?\bpurchase\b",
        re.IGNORECASE,
    ),
    # Direct order/trade-execution phrases (this product is alert/task records only — see
    # `backend/CLAUDE.md`'s "never add trading/execution columns" migration rule). These are
    # unambiguous as exact phrases; no legitimate research sentence contains them.
    re.compile(r"\bplace (an order|a trade)\b", re.IGNORECASE),
    re.compile(r"\bexecute (this|the) trade\b", re.IGNORECASE),
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
