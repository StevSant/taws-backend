from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import get_news_provider
from app.api.v1.schemas import NewsItemResponse
from app.domain.market.entities import AssetClass
from app.domain.market.ports import NewsProvider

router = APIRouter(prefix="/news", tags=["news"])

_MAX_SINCE_HOURS = 24 * 30
_MAX_LIMIT = 200


@router.get("")
async def list_news(
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    symbol: Annotated[str | None, Query()] = None,
    asset_class: Annotated[AssetClass | None, Query()] = None,
    since_hours: Annotated[int, Query(ge=1, le=_MAX_SINCE_HOURS)] = 48,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
) -> list[NewsItemResponse]:
    """Return recent news (HU1): each item carries `source`, `published_at`, and
    `related_symbols`, optionally filtered by instrument symbol / asset class / recency.
    """
    symbols = [symbol] if symbol else None
    items = await news_provider.fetch_news(
        symbols=symbols, asset_class=asset_class, since_hours=since_hours, limit=limit
    )
    return [NewsItemResponse.model_validate(item) for item in items]
