from enum import StrEnum


class NewsSkipReason(StrEnum):
    """Machine-readable explanation of why a `NewsItem` produced no Analyst `Signal` (issue #26).

    `AnalysisStatus` alone can't answer "why?": `skipped` collapses a deliberate cost decision,
    a duplicate, and an unlinkable article into one opaque state, and `pending` collapses "not
    looked at yet" with "we tried and it didn't clear the evidence floor". Both surfaced in the
    UI as the same ambiguous "Sin clasificar" tag. This enum is persisted next to
    `analysis_status` (migration 0014, nullable `news_items.skip_reason`) so the news-detail view
    can explain the outcome instead of showing a bare "no signal produced".

    Pairs with `analysis_status` — the status says *what* happened, the reason says *why*:

    - `no_linked_instrument` (`skipped`) — the article names no instrument in the curated
      universe, so there is nothing to classify it against: `GenerateSignal` is per-symbol.
    - `gated_low_relevance` (`skipped`) — deliberately not sent to the LLM: the pre-filter's
      combined relevance+materiality score fell below the configured floor.
    - `near_duplicate` (`skipped`) — another article with the same normalized title already
      covers this event for this instrument.
    - `compliance_blocked` (`skipped`) — classification ran but its output failed the
      compliance gate, so no signal was persisted. Not retried: re-running it would burn
      another LLM call on output that is very likely to be rejected again.
    - `insufficient_evidence` (stays `pending`) — fewer than the configured minimum of distinct
      news sources back this instrument right now. Retried on the next run: more sources can
      arrive later, and the check happens before any LLM call, so a retry is cheap.
    - `analysis_failed` (stays `pending`) — an unexpected failure (LLM outage, store error).
      Retried on the next run.
    """

    NO_LINKED_INSTRUMENT = "no_linked_instrument"
    GATED_LOW_RELEVANCE = "gated_low_relevance"
    NEAR_DUPLICATE = "near_duplicate"
    COMPLIANCE_BLOCKED = "compliance_blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ANALYSIS_FAILED = "analysis_failed"
