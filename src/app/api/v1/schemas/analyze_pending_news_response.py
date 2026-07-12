from pydantic import BaseModel, ConfigDict


class AnalyzePendingNewsResponse(BaseModel):
    """Response payload for `POST /api/v1/news/analyze-pending` (issue #2/#3):
    a summary of how many pending news items were analyzed, skipped by the pre-filter,
    or left pending after a failure this run.
    """

    model_config = ConfigDict(from_attributes=True)

    analyzed_count: int
    skipped_count: int
    failed_count: int
