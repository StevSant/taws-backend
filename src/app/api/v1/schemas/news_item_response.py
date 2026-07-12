from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NewsItemResponse(BaseModel):
    """Response payload for a single news item in `GET /api/v1/news`.

    Always carries `source`, `provider`, and `published_at` (HU1 criteria), plus
    `related_symbols` linking the article to instruments in the curated universe.
    `provider` is the fetching adapter's own identity (e.g. `"finnhub"`,
    `"marketaux"`), distinct from `source`, which is the article's publisher.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    summary: str
    url: str
    source: str
    provider: str
    published_at: datetime
    related_symbols: list[str]
