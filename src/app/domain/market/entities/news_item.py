from dataclasses import dataclass, field
from datetime import datetime

from app.domain.market.entities.analysis_status import AnalysisStatus
from app.domain.market.entities.news_category import NewsCategory
from app.domain.market.entities.news_entity import NewsEntity
from app.domain.market.entities.news_skip_reason import NewsSkipReason


@dataclass(frozen=True, slots=True)
class NewsItem:
    """A single news article, optionally linked to one or more instruments.

    `provider` is the fixed, stable identifier of the backend adapter that
    fetched this item (e.g. `"finnhub"`, `"marketaux"`), set unconditionally by
    every adapter. It is independent of `source`, which holds the article's
    own publisher/outlet name (e.g. "Economictimes.com") and can vary
    per-article even within the same provider.

    `entities` and `sentiment_score` are enrichment fields: providers that
    identify instruments in the text (e.g. Marketaux) populate them;
    `sentiment_score` is the average of the entity sentiments in [-1, +1].
    Plain sources leave them empty/None.

    `analysis_status`/`signal_id` (issue #1) track whether this specific article has
    been run through Analyst classification yet, independent of whether some *other*
    article about the same instrument already produced a `Signal`. Every `NewsProvider`
    adapter constructs items as `pending` (the default) — persistence
    (`NewsItemRepository`/`IngestNews`) is what backfills these to `analyzed`/`skipped`
    and keeps them stable across requests.

    `skip_reason` (issue #26) explains *why* an item produced no signal — the status alone
    can't distinguish a deliberate cost-saving gate from a duplicate, an unlinkable article,
    or an evidence shortfall. `None` on an `analyzed` item and on a `pending` one nothing has
    looked at yet; set by `AnalyzePendingNews`/`ForceAnalyzeNewsItem` on every other outcome.
    See `NewsSkipReason` for how each reason pairs with `analysis_status`.

    `category` (issue #69) is the article's *topic*, orthogonal to everything above: impact
    (the signal) says whether the news is good or bad for an instrument, category says what it
    is about. `IngestNews` assigns it on the independent, non-LLM `classify_news_category`
    path, so an item is categorized even when no signal is ever generated for it. `None` means
    nothing has classified it yet — distinct from `NewsCategory.UNCATEGORIZED`, which means the
    classifier looked and could not place it.
    """

    id: str
    title: str
    summary: str
    url: str
    source: str
    provider: str
    published_at: datetime
    related_symbols: list[str] = field(default_factory=list)
    entities: list[NewsEntity] = field(default_factory=list)
    sentiment_score: float | None = None
    analysis_status: AnalysisStatus = AnalysisStatus.PENDING
    signal_id: str | None = None
    image_url: str | None = None
    skip_reason: NewsSkipReason | None = None
    category: NewsCategory | None = None
