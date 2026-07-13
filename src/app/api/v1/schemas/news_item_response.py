from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.api.v1.schemas.news_entity_response import NewsEntityResponse
from app.domain.market.entities import AnalysisStatus, NewsCategory, NewsSkipReason


class NewsItemResponse(BaseModel):
    """Response payload for a single news item in `GET /api/v1/news`.

    Always carries `source`, `provider`, and `published_at` (HU1 criteria), plus
    `related_symbols` linking the article to instruments in the curated universe.

    `provider` is the fetching adapter's own identity (e.g. `"finnhub"`,
    `"marketaux"`), distinct from `source`, which is the article's publisher.

    `entities` and `sentiment_score` are enrichment fields populated only by
    sources that identify instruments in the text (currently Marketaux); both
    are `None` for every other source, never defaulted to a misleading value
    like `0`.

    `analysis_status`/`signal_id` (issue #1) are read from the persisted `news_items`
    store, so they reflect whatever a prior `AnalyzePendingNews` run decided — not a
    per-request client-side guess.

    `skip_reason` (issue #26) is the machine-readable *why* behind a missing signal — gated as
    low-relevance, near-duplicate, no linked instrument, insufficient evidence, compliance
    blocked. It is what lets the news-detail view explain the outcome instead of showing a bare
    "no signal produced". `None` means there's no explanation to give: the item was analyzed,
    or nothing has looked at it yet.

    `category` (issue #69) is the article's *topic*, and is independent of everything above:
    it is assigned on the ingest path by `classify_news_category`, so it is present even on
    items that never produced a signal. `None` means no classifier has run over the row yet
    (it predates migration 0018) — distinct from `NewsCategory.UNCATEGORIZED`, which means the
    classifier ran and could not place the item. Neither is the same thing as the *impact*
    bucket the UI shows as "Sin clasificar".
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
    entities: list[NewsEntityResponse] | None = None
    sentiment_score: float | None = None
    analysis_status: AnalysisStatus
    signal_id: str | None = None
    image_url: str | None = None
    skip_reason: NewsSkipReason | None = None
    category: NewsCategory | None = None

    @field_validator("entities", mode="before")
    @classmethod
    def _empty_entities_to_none(
        cls, value: list[NewsEntityResponse] | None
    ) -> list[NewsEntityResponse] | None:
        """Normalize the domain entity's `[]` default to `None`.

        `NewsItem.entities` defaults to an empty list for non-enriching
        sources; treat "no enrichment" the same as "field absent" here rather
        than surfacing an empty array that could be mistaken for "checked and
        found nothing".
        """
        return value or None
