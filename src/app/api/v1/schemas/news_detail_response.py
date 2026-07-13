from app.api.v1.schemas.news_asset_impact_response import NewsAssetImpactResponse
from app.api.v1.schemas.news_item_response import NewsItemResponse


class NewsDetailResponse(NewsItemResponse):
    """Response payload for `GET /api/v1/news/{news_id}` (issue #57).

    A strict superset of `NewsItemResponse` — every field the endpoint returned before is still
    there, at the same top-level key (`skip_reason` included), so this is purely additive and no
    existing client breaks. Subclassing rather than nesting is deliberate: wrapping the article
    in a `item: {...}` object would have been the cleaner-looking shape and a silent breaking
    change to every consumer of this endpoint.

    The two new fields are the page's remaining sections, moved server-side from the N+2 client
    round trips they used to cost:

    - `affected_instruments` — one row per instrument the article touches, with live price,
      % change, sentiment and (where the Analyst classified it) impact + confidence.
    - `related_news` — other recent articles related to this one, already ordered
      strongest-match-first by `NewsItemRepository.list_related`.
    """

    affected_instruments: list[NewsAssetImpactResponse] = []
    related_news: list[NewsItemResponse] = []
