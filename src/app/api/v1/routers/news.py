from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import get_news_provider
from app.api.v1.schemas import NewsItemResponse, NewsListResponse
from app.domain.market.entities import AssetClass
from app.domain.market.ports import NewsProvider

router = APIRouter(prefix="/news", tags=["news"])

_MAX_SINCE_HOURS = 24 * 30
_MAX_LIMIT = 200
_MAX_OFFSET = 10_000


@router.get("")
async def list_news(
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    symbol: Annotated[str | None, Query()] = None,
    asset_class: Annotated[AssetClass | None, Query()] = None,
    since_hours: Annotated[int, Query(ge=1, le=_MAX_SINCE_HOURS)] = 48,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0, le=_MAX_OFFSET)] = 0,
) -> NewsListResponse:
    """Return recent news (HU1), paginated: each item carries `source`, `provider`,
    `published_at`, and `related_symbols`, optionally filtered by instrument
    symbol / asset class / recency.

    `offset` resumes a previous fetch / pages beyond the first `limit` items;
    `has_more` on the response tells the caller whether a further page exists.
    `limit`/`since_hours` filtering behavior for callers that don't pass
    `offset` is unchanged (defaults to the first page, `offset=0`).
    """
    symbols = [symbol] if symbol else None
    # Ask the provider for one item past this page's end so `has_more` can be
    # derived without a separate, potentially-expensive upstream count query.
    items = await news_provider.fetch_news(
        symbols=symbols,
        asset_class=asset_class,
        since_hours=since_hours,
        limit=offset + limit + 1,
    )
    page = items[offset : offset + limit]
    has_more = len(items) > offset + limit
    return NewsListResponse(
        items=[NewsItemResponse.model_validate(item) for item in page],
        has_more=has_more,
    )
