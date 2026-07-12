from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.api.v1.dependencies import (
    get_embedding_provider,
    get_instrument_universe,
    get_llm_provider,
    get_market_data_provider,
    get_news_feed_refresher,
    get_news_item_repository,
    get_news_provider,
    get_signal_repository,
    get_vector_store,
)
from app.api.v1.schemas import AnalyzePendingNewsResponse, NewsItemResponse, NewsListResponse
from app.api.v1.schemas.localize_news_blurbs import (
    LocalizeNewsBlurbsRequest,
    LocalizeNewsBlurbsResponse,
    NewsBlurbResponse,
)
from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.market import NewsFeedRefresher
from app.application.market.use_cases import IngestNews, ListRecentNews
from app.application.market.use_cases.localize_news_blurbs import (
    LocalizeNewsBlurbs,
    NewsBlurbSource,
)
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
_MAX_OFFSET = 10_000


@router.get("")
async def list_news(
    background_tasks: BackgroundTasks,
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    news_feed_refresher: Annotated[NewsFeedRefresher, Depends(get_news_feed_refresher)],
    settings: Annotated[Settings, Depends(get_settings)],
    symbol: Annotated[str | None, Query()] = None,
    asset_class: Annotated[AssetClass | None, Query()] = None,
    since_hours: Annotated[int, Query(ge=1, le=_MAX_SINCE_HOURS)] = 48,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0, le=_MAX_OFFSET)] = 0,
) -> NewsListResponse:
    """Return recent news (HU1), paginated: each item carries `source`, `provider`,
    `published_at`, `related_symbols`, and `analysis_status` (issue #1), optionally
    filtered by instrument symbol / asset class / recency.

    Served DB-first (taws#71): the page comes out of the persisted `news_items` store
    (`ListRecentNews`), and the upstream provider fan-out that keeps that store fresh runs
    in a background task *after* this response is flushed (`NewsFeedRefresher`, throttled).
    Previously this handler re-aggregated Yahoo/RSS/Finnhub synchronously and persisted
    them before answering, which on a cold cache overshot the radar client's request
    timeout and took the whole page down with it. A cold store still falls back to that
    blocking path so the first-ever caller isn't served an empty feed.

    Persist-then-read (issue #1) is unchanged, just moved off the request path:
    `analysis_status` still reflects whatever a prior `AnalyzePendingNews` run decided,
    because it is read from the same persisted rows.

    `offset` resumes a previous fetch / pages beyond the first `limit` items;
    `has_more` on the response tells the caller whether a further page exists.
    `limit`/`since_hours` filtering behavior for callers that don't pass
    `offset` is unchanged (defaults to the first page, `offset=0`).
    """
    symbols = [symbol] if symbol else None
    use_case = ListRecentNews(
        news_item_repository=news_item_repository,
        instrument_universe=instrument_universe,
        ingest_news=IngestNews(
            news_provider=news_provider,
            news_item_repository=news_item_repository,
            signal_repository=signal_repository,
        ),
        db_first_enabled=settings.news_db_first_enabled,
        min_persisted_items=settings.news_db_first_min_items,
    )
    # Ask for one item past this page's end so `has_more` can be derived without a
    # separate, potentially-expensive count query.
    items = await use_case.execute(
        symbols=symbols,
        asset_class=asset_class,
        since_hours=since_hours,
        limit=offset + limit + 1,
    )
    # Keyed on the *canonical* universe symbol so an unknown `?symbol=` string can't grow
    # the refresher's throttle map without bound — see `NewsFeedRefresher`.
    instrument = instrument_universe.by_symbol(symbol) if symbol else None
    background_tasks.add_task(
        news_feed_refresher.refresh,
        symbol=instrument.symbol if instrument else None,
        asset_class=asset_class,
        since_hours=since_hours,
    )
    page = items[offset : offset + limit]
    has_more = len(items) > offset + limit
    return NewsListResponse(
        items=[NewsItemResponse.model_validate(item) for item in page],
        has_more=has_more,
    )


@router.post("/blurbs")
async def localize_news_blurbs(
    body: LocalizeNewsBlurbsRequest,
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> LocalizeNewsBlurbsResponse:
    """Return short locale-aware blurbs for timeline cards (title stays original).

    Used by the Radar news timeline when the UI locale is Spanish and upstream
    headlines/summaries arrive in English. Cached in-process per news id.
    """
    use_case = LocalizeNewsBlurbs(llm_provider)
    blurbs = await use_case.execute(
        [
            NewsBlurbSource(id=item.id, title=item.title, summary=item.summary)
            for item in body.items
        ],
        locale=body.locale,
    )
    return LocalizeNewsBlurbsResponse(
        items=[NewsBlurbResponse(id=row.id, blurb=row.blurb) for row in blurbs]
    )


@router.get("/{news_id}")
async def get_news_item(
    news_id: str,
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
) -> NewsItemResponse:
    """Return a single persisted news item by its `news_items.id` (issue #38), or 404.

    Reads straight from the `news_items` store — the item must already have been
    persisted by a prior `GET /api/v1/news` (persist-then-read) — so `analysis_status`
    reflects whatever a prior `AnalyzePendingNews` run decided. Not user-scoped (public
    read, same visibility model as the list endpoint).
    """
    item = await news_item_repository.get_by_id(news_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News item not found")
    return NewsItemResponse.model_validate(item)


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
