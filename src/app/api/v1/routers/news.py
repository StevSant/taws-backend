from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies import (
    get_embedding_provider,
    get_instrument_universe,
    get_llm_provider,
    get_market_data_provider,
    get_news_item_repository,
    get_news_prefilter_policy,
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
from app.application.market.use_cases import IngestNews
from app.application.market.use_cases.localize_news_blurbs import (
    LocalizeNewsBlurbs,
    NewsBlurbSource,
)
from app.application.signals import (
    NewsItemNotAnalyzableError,
    NewsItemNotFoundError,
    NewsPrefilterPolicy,
)
from app.application.signals.use_cases import (
    AnalyzePendingNews,
    ForceAnalyzeNewsItem,
    GenerateSignal,
)
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
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    symbol: Annotated[str | None, Query()] = None,
    asset_class: Annotated[AssetClass | None, Query()] = None,
    since_hours: Annotated[int, Query(ge=1, le=_MAX_SINCE_HOURS)] = 48,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0, le=_MAX_OFFSET)] = 0,
) -> NewsListResponse:
    """Return recent news (HU1), paginated: each item carries `source`, `provider`,
    `published_at`, `related_symbols`, and `analysis_status` (issue #1), optionally
    filtered by instrument symbol / asset class / recency.

    Persist-then-read (issue #1): fetched items are upserted into the `news_items`
    store (deduped by URL) before being returned, so `analysis_status` reflects
    whatever a prior `AnalyzePendingNews` run decided and survives across requests
    instead of being recomputed from scratch.

    `offset` resumes a previous fetch / pages beyond the first `limit` items;
    `has_more` on the response tells the caller whether a further page exists.
    `limit`/`since_hours` filtering behavior for callers that don't pass
    `offset` is unchanged (defaults to the first page, `offset=0`).
    """
    symbols = [symbol] if symbol else None
    use_case = IngestNews(
        news_provider=news_provider,
        news_item_repository=news_item_repository,
        signal_repository=signal_repository,
    )
    # Ask the pipeline for one item past this page's end so `has_more` can be
    # derived without a separate, potentially-expensive upstream count query.
    items = await use_case.execute(
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
    prefilter_policy: Annotated[NewsPrefilterPolicy, Depends(get_news_prefilter_policy)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalyzePendingNewsResponse:
    """Analyze every persisted news item still `pending`, server-side (issue #2).

    Replaces the frontend's N-sequential-per-instrument HTTP calls
    (`radar-store.ts`'s `generateAllUnclassified()`) with one backend-owned batch pass:
    groups pending items by instrument, applies a cheap pre-filter before any LLM call
    (issues #3/#26), then classifies the remaining groups with bounded concurrency. Not
    user-scoped — same visibility model as `GET /api/v1/news` and `POST
    /api/v1/signals/generate`.

    The same pass runs on a schedule (`NEWS_ANALYSIS_POLL_INTERVAL_MINUTES`, toggleable via
    `NEWS_ANALYSIS_ENABLED`), so this endpoint is a "don't wait for the next tick" trigger
    rather than the only way analysis ever happens. The response's `skipped_by_reason` /
    `failed_by_reason` breakdowns are the fastest way to see whether the gate is tuned right.
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
        prefilter_policy=prefilter_policy,
        min_distinct_sources=settings.min_distinct_news_sources,
        max_concurrency=settings.news_analysis_max_concurrency,
        batch_limit=settings.news_analysis_batch_limit,
    )
    result = await use_case.execute(locale=settings.default_locale)
    return AnalyzePendingNewsResponse.model_validate(result)


@router.post("/{news_id}/analyze", status_code=status.HTTP_200_OK)
async def force_analyze_news_item(
    news_id: str,
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    market_data_provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> NewsItemResponse:
    """Force-classify ONE news item, bypassing the pre-filter — the "Analizar ahora" button
    (issue #27).

    The manual counterpart to the gate: `POST /news/analyze-pending` deliberately *skips* the
    low-relevance item the user is looking at, and `POST /signals/generate` is per-symbol and
    can't target a single article. This runs the same `GenerateSignal` pipeline for the item's
    linked instrument, links the resulting signal, and updates `analysis_status` — returning
    the refreshed item so the detail page can render the new signal in place.

    Bypassing `_prefilter` is the whole point; the evidence floor and the compliance gate still
    apply (they're correctness guarantees, not cost optimizations). Every non-success outcome
    is a 422 whose `detail.skip_reason` is the machine-readable `NewsSkipReason` just persisted
    on the item, so the frontend can explain it rather than showing an opaque failure.

    Not user-scoped — same visibility model as the rest of this router.
    """
    use_case = ForceAnalyzeNewsItem(
        news_item_repository=news_item_repository,
        generate_signal=GenerateSignal(
            news_provider=news_provider,
            market_data_provider=market_data_provider,
            instrument_universe=instrument_universe,
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
            retry_max_attempts=settings.signal_classification_retry_max_attempts,
            retry_backoff_base_seconds=settings.signal_classification_retry_backoff_base_seconds,
        ),
    )
    try:
        item = await use_case.execute(news_id, locale=settings.default_locale)
    except NewsItemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="News item not found"
        ) from exc
    except NewsItemNotAnalyzableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": str(exc), "skip_reason": exc.skip_reason.value},
        ) from exc
    return NewsItemResponse.model_validate(item)
