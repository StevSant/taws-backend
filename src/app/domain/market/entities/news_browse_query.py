from dataclasses import dataclass

from app.domain.market.entities.analysis_status import AnalysisStatus
from app.domain.market.entities.news_category import NewsCategory
from app.domain.market.entities.news_sort_field import NewsSortField
from app.domain.market.entities.sentiment_filter import SentimentFilter
from app.domain.market.entities.sort_direction import SortDirection


@dataclass(frozen=True, slots=True)
class NewsBrowseQuery:
    """Fully-resolved query for one page of persisted news (`GET /api/v1/news/browse`).

    `symbols` is the *resolved* instrument filter: the `BrowseNews` use case expands
    an `asset_class` into its member symbols before building this, so the repository
    only ever sees concrete symbols and never has to know about the instrument
    universe. `page` is 1-based.
    """

    symbols: list[str] | None = None
    source: str | None = None
    provider: str | None = None
    sentiment: SentimentFilter | None = None
    category: NewsCategory | None = None
    analysis_status: AnalysisStatus | None = None
    search: str | None = None
    since_hours: int = 48
    sort_by: NewsSortField = NewsSortField.PUBLISHED_AT
    sort_dir: SortDirection = SortDirection.DESC
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
