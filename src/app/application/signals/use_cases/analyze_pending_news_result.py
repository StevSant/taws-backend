from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalyzePendingNewsResult:
    """Outcome summary of one `AnalyzePendingNews.execute()` batch run (issue #2/#3).

    `failed_count` items are left `pending` (not `skipped`) for retry on the next run —
    a failure (e.g. `InsufficientEvidenceError`, an LLM outage) isn't a triage decision.
    """

    analyzed_count: int
    skipped_count: int
    failed_count: int
