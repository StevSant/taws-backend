from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.news_item_response import NewsItemResponse


class NewsBrowseResponse(BaseModel):
    """Paginated envelope for `GET /api/v1/news/browse`.

    Unlike `NewsListResponse`'s `has_more` (all the provider-fed feed can afford to know),
    `total` is the exact size of the full filtered set before pagination — the number a
    numbered "Página X de Y" pager needs to know how many pages exist.
    """

    model_config = ConfigDict(from_attributes=True)

    items: list[NewsItemResponse]
    total: int
    page: int
    page_size: int
