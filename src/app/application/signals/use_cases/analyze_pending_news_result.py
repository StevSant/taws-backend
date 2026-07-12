from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AnalyzePendingNewsResult:
    """Outcome summary of one `AnalyzePendingNews.execute()` batch run (issue #2/#3/#26).

    `failed_count` items are left `pending` (not `skipped`) for retry on the next run —
    a failure (e.g. `InsufficientEvidenceError`, an LLM outage) isn't a triage decision.

    The two breakdowns (issue #26) map a `NewsSkipReason` value onto how many items got it this
    run — the observability the gate needs to be tuned honestly. Bare totals can't answer the
    question that matters ("is the pre-filter gating too hard, or is nothing linkable in the
    first place?"): a run of 200 skipped items is healthy if they're `near_duplicate` and a bug
    if they're all `gated_low_relevance`. Keyed by the enum's string value so the response
    schema can serialize them straight to JSON.
    """

    analyzed_count: int
    skipped_count: int
    failed_count: int
    skipped_by_reason: dict[str, int] = field(default_factory=dict)
    failed_by_reason: dict[str, int] = field(default_factory=dict)
