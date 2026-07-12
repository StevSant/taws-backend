from enum import StrEnum


class AnalysisStatus(StrEnum):
    """Lifecycle of a persisted `NewsItem` with respect to Analyst classification.

    `pending` — not yet looked at (default for a newly-ingested item).
    `analyzed` — an LLM classification ran and produced a `Signal` (see `NewsItem.signal_id`).
    `skipped` — deliberately not sent to the LLM (issue #3's pre-filter: low ticker-relevance,
    a duplicate of an already-classified item, or no linked instrument at all).
    """

    PENDING = "pending"
    ANALYZED = "analyzed"
    SKIPPED = "skipped"
