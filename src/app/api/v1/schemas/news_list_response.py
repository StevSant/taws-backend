from pydantic import BaseModel

from app.api.v1.schemas.news_item_response import NewsItemResponse


class NewsListResponse(BaseModel):
    """Paginated envelope for `GET /api/v1/news`.

    `has_more` tells the caller whether items exist beyond this page
    (`offset + len(items)`), so a client can page forward with `offset`
    without needing an expensive, exact corpus-wide count upfront.
    """

    items: list[NewsItemResponse]
    has_more: bool
