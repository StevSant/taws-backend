from app.api.v1.schemas.news_asset_impact_response import NewsAssetImpactResponse
from app.api.v1.schemas.news_detail_response import NewsDetailResponse
from app.api.v1.schemas.news_item_response import NewsItemResponse
from app.application.market.use_cases import NewsDetail


def map_news_detail_to_response(detail: NewsDetail) -> NewsDetailResponse:
    """Map the `BuildNewsDetail` result onto the wire schema.

    The article's own fields are mapped by `NewsItemResponse` (one place, so the detail endpoint
    and the list endpoint can never drift on how a news item is serialized) and then spread into
    the detail response, which extends it. Only the two enrichment collections are mapped here.
    """
    article = NewsItemResponse.model_validate(detail.item)
    return NewsDetailResponse(
        **article.model_dump(),
        affected_instruments=[
            NewsAssetImpactResponse.model_validate(impact) for impact in detail.affected_instruments
        ],
        related_news=[NewsItemResponse.model_validate(item) for item in detail.related_news],
    )
