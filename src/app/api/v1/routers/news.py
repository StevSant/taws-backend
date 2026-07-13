from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.dependencies import (
    get_analyze_pending_news_use_case,
    get_fast_llm_provider,
    get_force_analyze_news_item_use_case,
    get_instrument_universe,
    get_news_item_repository,
    get_news_provider,
    get_signal_repository,
)
from app.api.v1.schemas import (
    AnalyzePendingNewsResponse,
    NewsBrowseResponse,
    NewsFacetsResponse,
    NewsItemResponse,
    NewsListResponse,
)
from app.api.v1.schemas.localize_news_blurbs import (
    LocalizeNewsBlurbsRequest,
    LocalizeNewsBlurbsResponse,
    NewsBlurbResponse,
)
from app.application.market.use_cases import BrowseNews, IngestNews
from app.application.market.use_cases.localize_news_blurbs import (
    LocalizeNewsBlurbs,
    NewsBlurbSource,
)
from app.application.signals import NewsItemNotAnalyzableError, NewsItemNotFoundError
from app.application.signals.use_cases import AnalyzePendingNews, ForceAnalyzeNewsItem
from app.core.config import Settings, get_settings
from app.domain.agents.ports import LLMProvider
from app.domain.market.entities import (
    AnalysisStatus,
    AssetClass,
    NewsBrowseQuery,
    NewsCategory,
    NewsSortField,
    SentimentFilter,
    SortDirection,
)
from app.domain.market.ports import InstrumentUniverse, NewsItemRepository, NewsProvider
from app.domain.signals.ports import SignalRepository

router = APIRouter(prefix="/news", tags=["news"])

_MAX_SINCE_HOURS = 24 * 30
_MAX_LIMIT = 200
_MAX_OFFSET = 10_000
# Longest accepted `q`. A headline search is a few words; anything longer is a client bug or
# an attempt to build an expensive `ilike` scan.
_SEARCH_MAX_LEN = 60
# Deepest page the browse pager will serve. `_MAX_OFFSET` bounds the same thing for the
# offset-based `GET /api/v1/news`; this is its page-based equivalent.
_MAX_PAGE = 1_000


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
    llm_provider: Annotated[LLMProvider, Depends(get_fast_llm_provider)],
) -> LocalizeNewsBlurbsResponse:
    """Return short locale-aware blurbs for timeline cards (title stays original).

    Used by the Radar news timeline when the UI locale is Spanish and upstream
    headlines/summaries arrive in English. Cached in-process per news id.

    Fast tier (issue #28): shortening and translating a headline is the cheapest kind of LLM
    call in the codebase, and it fans out per news item — exactly the wrong place to spend
    reasoning-tier tokens.
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


@router.get("/browse")
async def browse_news(
    news_provider: Annotated[NewsProvider, Depends(get_news_provider)],
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
    signal_repository: Annotated[SignalRepository, Depends(get_signal_repository)],
    instrument_universe: Annotated[InstrumentUniverse, Depends(get_instrument_universe)],
    settings: Annotated[Settings, Depends(get_settings)],
    symbol: Annotated[str | None, Query()] = None,
    asset_class: Annotated[AssetClass | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    provider: Annotated[str | None, Query()] = None,
    sentiment: Annotated[SentimentFilter | None, Query()] = None,
    category: Annotated[NewsCategory | None, Query()] = None,
    analysis_status: Annotated[AnalysisStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=_SEARCH_MAX_LEN)] = None,
    since_hours: Annotated[int, Query(ge=1, le=_MAX_SINCE_HOURS)] = 48,
    sort_by: Annotated[NewsSortField, Query()] = NewsSortField.PUBLISHED_AT,
    sort_dir: Annotated[SortDirection, Query()] = SortDirection.DESC,
    page: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> NewsBrowseResponse:
    """Browse the persisted news archive: server-side filter + sort + exact total (issue #70).

    The DB-backed counterpart to `GET /api/v1/news`. That endpoint is provider-fed — it fetches
    upstreams on every call and slices in Python, so it can only ever say `has_more` and can only
    order within the slice a provider handed it. This one reads the `news_items` store, so it can
    report `total` (what a numbered "Página X de Y" pager needs) and sort/filter across the whole
    corpus.

    Since nothing ingests news on a schedule, a best-effort `IngestNews` refresh runs on **page 1
    only** — the archive stays fresh without an upstream fetch on every page click, and a failed
    refresh still serves the DB read.
    """
    resolved_page_size = min(
        page_size or settings.news_browse_default_page_size, settings.news_browse_max_page_size
    )
    query = NewsBrowseQuery(
        symbols=[symbol] if symbol else None,
        source=source,
        provider=provider,
        sentiment=sentiment,
        category=category,
        analysis_status=analysis_status,
        search=q,
        since_hours=since_hours,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=resolved_page_size,
    )
    use_case = BrowseNews(
        news_item_repository=news_item_repository,
        instrument_universe=instrument_universe,
        ingest_news=IngestNews(
            news_provider=news_provider,
            news_item_repository=news_item_repository,
            signal_repository=signal_repository,
        ),
    )
    result = await use_case.execute(query=query, asset_class=asset_class)
    return NewsBrowseResponse.model_validate(result)


@router.get("/facets")
async def list_news_facets(
    news_item_repository: Annotated[NewsItemRepository, Depends(get_news_item_repository)],
) -> NewsFacetsResponse:
    """Distinct `source`/`provider` values in the store, for the browse filter dropdowns.

    Read from the corpus rather than hardcoded, so the dropdowns can only ever offer a value
    that some article actually carries.
    """
    facets = await news_item_repository.list_facets()
    return NewsFacetsResponse.model_validate(facets)


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
    use_case: Annotated[AnalyzePendingNews, Depends(get_analyze_pending_news_use_case)],
    settings: Annotated[Settings, Depends(get_settings)],
    locale: Annotated[str | None, Query(min_length=2, max_length=35)] = None,
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

    `locale` picks the language the resulting signals are written in (issue #67). Not
    user-scoped, so there is no `preferred_locale` to fall back to: an omitted `locale` means
    `Settings.default_locale`, and a caller that wants another language says so — the same
    contract as `GET /instruments/enriched` and `POST /signals/generate`.
    """
    result = await use_case.execute(locale=locale or settings.default_locale)
    return AnalyzePendingNewsResponse.model_validate(result)


@router.post("/{news_id}/analyze", status_code=status.HTTP_200_OK)
async def force_analyze_news_item(
    news_id: str,
    use_case: Annotated[ForceAnalyzeNewsItem, Depends(get_force_analyze_news_item_use_case)],
    settings: Annotated[Settings, Depends(get_settings)],
    locale: Annotated[str | None, Query(min_length=2, max_length=35)] = None,
) -> NewsItemResponse:
    """Force-classify ONE news item, bypassing the pre-filter — the "Analizar ahora" button
    (issue #27).

    The manual counterpart to the gate: `POST /news/analyze-pending` deliberately *skips* the
    low-relevance item the user is looking at, and `POST /signals/generate` is per-symbol and
    can't target a single article. This runs the same `GenerateSignal` pipeline for the item's
    linked instrument, links the resulting signal, and updates `analysis_status` — returning
    the refreshed item so the detail page can render the new signal in place.

    Bypasses BOTH gates, and only these two: the pre-filter (issue #27) and, since issue #29,
    the freshness cache (`force=True`). Skipping the cache is essential here — a user pressing
    "Analizar ahora" on an article that was passed over must get a real analysis of it, not a
    signal generated ten minutes ago from different news. The evidence floor and the compliance
    gate still apply: those are correctness guarantees, not cost optimizations. Every
    non-success outcome is a 422 whose `detail.skip_reason` is the machine-readable
    `NewsSkipReason` just persisted on the item, so the frontend can explain it rather than
    showing an opaque failure.

    Not user-scoped — same visibility model as the rest of this router. `locale` therefore
    works exactly as it does on `POST /news/analyze-pending`: the UI sends the language it is
    displaying, and an omitted value means `Settings.default_locale` (issue #67).
    """
    try:
        item = await use_case.execute(news_id, locale=locale or settings.default_locale)
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
