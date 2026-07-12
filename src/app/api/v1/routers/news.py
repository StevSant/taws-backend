from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.v1.dependencies import (
    get_embedding_provider,
    get_instrument_universe,
    get_llm_provider,
    get_market_data_provider,
    get_news_item_repository,
    get_news_provider,
    get_signal_repository,
    get_vector_store,
)
from app.api.v1.schemas import AnalyzePendingNewsResponse, NewsItemResponse
from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.market.use_cases import IngestNews
from app.application.signals.use_cases import AnalyzePendingNews
from app.core.config import Settings, get_settings
from app.domain.agents.ports import EmbeddingProvider, LLMProvider, VectorStore
from app.domain.market.entities import AssetClass
from app.domain.market.ports import (
    InstrumentUniverse,
    MarketDataProvider,
    NewsItemRepository,
    NewsProvider,
)
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
    whatever a prior `AnalyzePendingNews` run decided and survives across requests
    instead of being recomputed from scratch on every call.
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


@router.post("/analyze-pending", status_code=status.HTTP_200_OK)
async def analyze_pending_news(
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    market_data_provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalyzePendingNewsResponse:
    """Analyze every persisted news item still `pending`, server-side (issue #2).

    Replaces the frontend's N-sequential-per-instrument HTTP calls
    (`radar-store.ts`'s `generateAllUnclassified()`) with one backend-owned batch pass:
    groups pending items by instrument, applies a cheap pre-filter before any LLM call
    (issue #3), then classifies the remaining groups with bounded concurrency. Not
    user-scoped — same visibility model as `GET /api/v1/news` and `POST
    /api/v1/signals/generate`.
    """
    use_case = AnalyzePendingNews(
        news_item_repository=news_item_repository,
        instrument_universe=instrument_universe,
        market_data_provider=market_data_provider,
        news_provider=news_provider,
        signal_repository=signal_repository,
        llm_provider=llm_provider,
        find_historical_analogs=FindHistoricalAnalogs(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            top_k=settings.historical_analogs_top_k,
        ),
        index_signal_analog=IndexSignalAnalog(
            embedding_provider=embedding_provider, vector_store=vector_store
        ),
        min_distinct_sources=settings.min_distinct_news_sources,
        relevance_skip_threshold=settings.news_relevance_skip_threshold,
        max_concurrency=settings.news_analysis_max_concurrency,
        batch_limit=settings.news_analysis_batch_limit,
    )
    result = await use_case.execute(locale=settings.default_locale)
    return AnalyzePendingNewsResponse.model_validate(result)
