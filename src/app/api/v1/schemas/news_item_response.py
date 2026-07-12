from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.market.entities import AnalysisStatus


class NewsItemResponse(BaseModel):
    """Response payload for a single news item in `GET /api/v1/news`.

    Always carries `source` and `published_at` (HU1 criteria), plus
    `related_symbols` linking the article to instruments in the curated universe.
    `analysis_status`/`signal_id` (issue #1) are read from the persisted `news_items`
    store, so they reflect whatever a prior `AnalyzePendingNews` run decided — not a
    per-request client-side guess.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    summary: str
    url: str
    source: str
    published_at: datetime
    related_symbols: list[str]
    analysis_status: AnalysisStatus
    signal_id: str | None = None
