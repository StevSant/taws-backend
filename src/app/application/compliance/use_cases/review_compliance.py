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
#
# Known residual limitation (accepted, not chased further — see third review round): a fixed
# proximity window can still be evaded by padding a long enough qualifying clause between the
# two trigger words (e.g. "We guarantee — [90-char aside] — outsized returns"). This is a
# structural limit of regex-based proximity matching, not a bug to fix by widening windows
# further — wider windows trade this false negative for new false positives on unrelated text.
# An LLM-based semantic check would close this gap but was deliberately NOT chosen here: this
# reviewer's whole value is being deterministic and auditable (see class docstring), which an
# LLM judging free text is not.
_BANNED_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Promised/guaranteed returns: "guarantee" (or "guarantees"/"guaranteed", or the synonym
    # "assured"/"assure") occurring near "return(s)"/"profit(s)"/"gain(s)"/"upside", in either
    # order, within a window generous enough to cover natural phrasing like "we guarantee
    # investors will see strong returns" (27 chars between the two words) without also matching
    # on totally unrelated sentences. "assured" alone (e.g. "I am assured by the team...") does
    # NOT match — the return/profit/gain/upside term must still be present nearby.
    re.compile(
        r"\b(guarantee[sd]?|assured?)\b.{0,40}?\b(return|profit|gain|upside)s?\b", re.IGNORECASE
    ),
    re.compile(
        r"\b(return|profit|gain|upside)s?\b.{0,40}?\b(guarantee[sd]?|assured?)\b", re.IGNORECASE
    ),
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
    # NOTE: "purchase" execution instructions are intentionally NOT a proximity pattern here —
    # see `_find_purchase_violation` below. Unlike "buy"/"sell", "purchase" alone is ambiguous
    # (legitimate hedging language, or third-party historical narration) and needs a 3-way
    # co-occurrence + exclusion check that a single regex proximity pair can't express cleanly.
    #
    # Direct order/trade-execution phrases (this product is alert/task records only — see
    # `backend/CLAUDE.md`'s "never add trading/execution columns" migration rule). These are
    # unambiguous as exact phrases; no legitimate research sentence contains them.
    re.compile(r"\bplace (an order|a trade)\b", re.IGNORECASE),
    re.compile(r"\bexecute (this|the) trade\b", re.IGNORECASE),
)

# "Purchase" execution check — a windowed keyword-overlap check rather than a proximity regex
# pair (see the NOTE above `_BANNED_PHRASE_PATTERNS`). A prior round scoped "purchase" to
# require a nearby security/trade object (so generic hedging nouns wouldn't trigger it), but
# that alone still over-triggered on two real shapes: hedging instruments ("purchase puts to
# hedge your position") and third-party historical narration ("increased its purchase of
# shares last quarter") — neither is an execution recommendation directed at the reader. This
# check requires an object AND a recommendation-shaped word in the same window, AND requires
# no hedging/protective word in that window, so it's the co-occurrence of "trade object +
# recommendation language + no hedging term" that decides it, not the object vocabulary alone.
_PURCHASE_WINDOW = 40  # chars either side of "purchase"; matches the other patterns' window
_PURCHASE_TOKEN_PATTERN = re.compile(r"\bpurchase\b", re.IGNORECASE)
_PURCHASE_WORD_PATTERN = re.compile(r"[a-z']+")
_PURCHASE_OBJECT_WORDS = frozenset(
    {"stock", "share", "shares", "position", "security", "equity", "equities", "ticker"}
)
_PURCHASE_RECOMMENDATION_WORDS = frozenset(
    {"should", "must", "recommend", "advise", "consider", "now", "immediately"}
)
_PURCHASE_HEDGING_WORDS = frozenset(
    {
        "put",
        "puts",
        "option",
        "options",
        "hedge",
        "hedges",
        "protect",
        "protects",
        "protection",
        "insurance",
    }
)


def _find_purchase_violation(text: str) -> str | None:
    """Return the first offending window around a "purchase" occurrence, or `None`.

    For each "purchase" token, looks at a fixed character window around it and flags only when
    ALL of the following hold in that same window:
      1. a security/trade object is present (stock, share(s), position, security, equity,
         equities, ticker) — otherwise "purchase" isn't about a tradeable instrument;
      2. a recommendation-shaped word is present (should, must, recommend, advise, consider,
         now, immediately) — otherwise the sentence reads as descriptive/historical, not a
         recommendation directed at the reader;
      3. no hedging/protective word is present (put(s), option(s), hedge(s), protect*,
         insurance) — hedging is legitimate research content, even when phrased with a
         recommendation word (e.g. "you should purchase puts to hedge your position").

    All three checks share one window, so a hedging word suppresses the match regardless of
    whether it sits between "purchase" and the object or between "purchase" and the
    recommendation word.
    """
    for token_match in _PURCHASE_TOKEN_PATTERN.finditer(text):
        start = max(0, token_match.start() - _PURCHASE_WINDOW)
        end = min(len(text), token_match.end() + _PURCHASE_WINDOW)
        window = text[start:end]
        words = set(_PURCHASE_WORD_PATTERN.findall(window.lower()))
        if not words & _PURCHASE_OBJECT_WORDS:
            continue
        if not words & _PURCHASE_RECOMMENDATION_WORDS:
            continue
        if words & _PURCHASE_HEDGING_WORDS:
            continue
        return window.strip()
    return None


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
    2. **No banned phrases** — a fixed regex scan (`_BANNED_PHRASE_PATTERNS`), plus one
       windowed keyword-overlap check for the ambiguous "purchase" case
       (`_find_purchase_violation`), over the candidate's free-text fields (e.g. an Analyst
       classification's `reasoning`, an Advisor briefing's `summary`) for promised/guaranteed-
       return language and execution/trade instructions.

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

        purchase_violation = _find_purchase_violation(combined_text)
        if purchase_violation is not None and purchase_violation.lower() not in seen_phrases:
            seen_phrases.add(purchase_violation.lower())
            violations.append(
                ComplianceViolation(
                    rule=_RULE_BANNED_PHRASE,
                    detail=f"Output contains banned phrase: {purchase_violation!r}",
                )
            )

        return ComplianceCheckResult(passed=not violations, violations=violations)
