from pydantic import BaseModel, ConfigDict, Field


class AnalyzePendingNewsResponse(BaseModel):
    """Response payload for `POST /api/v1/news/analyze-pending` (issue #2/#3/#26):
    a summary of how many pending news items were analyzed, skipped by the pre-filter,
    or left pending after a failure this run.

    The two breakdowns map a `NewsSkipReason` value onto how many items got it this run. They
    are what make the gate tunable: the bare totals can't distinguish "the pre-filter is too
    aggressive" (`gated_low_relevance` dominating) from "nothing we ingest is linkable to the
    universe" (`no_linked_instrument` dominating) from "we're healthily deduping wire copy"
    (`near_duplicate` dominating) — and those three call for opposite fixes.
    """

    model_config = ConfigDict(from_attributes=True)

    analyzed_count: int
    skipped_count: int
    failed_count: int
    # Terminal outcomes: no_linked_instrument, gated_low_relevance, near_duplicate,
    # compliance_blocked.
    skipped_by_reason: dict[str, int] = Field(default_factory=dict)
    # Retryable outcomes — these items stay `pending` and are re-attempted on the next run:
    # insufficient_evidence, analysis_failed.
    failed_by_reason: dict[str, int] = Field(default_factory=dict)
