from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.dependencies import (
    get_news_item_repository,
    get_news_provider,
    get_signal_repository,
)
from app.api.v1.schemas import NewsItemResponse
from app.application.market.use_cases import IngestNews
from app.domain.market.entities import AssetClass
from app.domain.market.ports import NewsItemRepository, NewsProvider
from app.domain.signals.ports import SignalRepository

router = APIRouter(prefix="/news", tags=["news"])

_MAX_SINCE_HOURS = 24 * 30
_MAX_LIMIT = 200


@router.get("")
async def list_news(
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    symbol: Annotated[str | None, Query()] = None,
    asset_class: Annotated[AssetClass | None, Query()] = None,
    since_hours: Annotated[int, Query(ge=1, le=_MAX_SINCE_HOURS)] = 48,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
) -> list[NewsItemResponse]:
    """Return recent news (HU1): each item carries `source`, `published_at`,
    `related_symbols`, and `analysis_status` (issue #1), optionally filtered by
    instrument symbol / asset class / recency.

    Persist-then-read (issue #1): fetched items are upserted into the `news_items`
    store (deduped by URL) before being returned, so `analysis_status` reflects
    whatever a prior analysis run decided and survives across requests instead of
    being recomputed from scratch on every call.
    """
    symbols = [symbol] if symbol else None
    use_case = IngestNews(
        news_provider=news_provider,
        news_item_repository=news_item_repository,
        signal_repository=signal_repository,
    )
    items = await use_case.execute(
        symbols=symbols, asset_class=asset_class, since_hours=since_hours, limit=limit
    )
    return [NewsItemResponse.model_validate(item) for item in items]
