from dataclasses import dataclass, field

from app.application.market.use_cases.news_asset_impact import NewsAssetImpact
from app.domain.market.entities import NewsItem


@dataclass(frozen=True, slots=True)
class NewsDetail:
    """Result of `BuildNewsDetail.execute(...)`: one news article plus everything the
    news-detail page renders around it (issue #57).

    Not persisted — a computed-on-demand value object assembled from existing use cases and
    ports, same role as `application.quant.MarketStats`. `item` is the article exactly as
    persisted (so every field `GET /api/v1/news/{id}` already returned stays intact, including
    `skip_reason`); the other two are the additive enrichment.
    """

    item: NewsItem
    affected_instruments: list[NewsAssetImpact] = field(default_factory=list)
    related_news: list[NewsItem] = field(default_factory=list)
