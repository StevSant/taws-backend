from dataclasses import dataclass

from app.domain.market.entities.news_item import NewsItem


@dataclass(frozen=True, slots=True)
class PaginatedNewsItems:
    """One page of persisted news plus the total size of the full filtered set.

    `total` counts every row matching the filters *before* pagination — that count
    is what lets the frontend render numbered "Página X de Y" controls, which
    `GET /api/v1/news`'s `has_more` flag can never support.
    """

    items: list[NewsItem]
    total: int
    page: int
    page_size: int
