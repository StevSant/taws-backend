from pydantic import BaseModel, ConfigDict


class NewsEntityResponse(BaseModel):
    """Response payload for one instrument entity identified within a news article.

    Populated only for enrichment-capable sources (currently Marketaux);
    `match_score` and `sentiment_score` are `None` when the upstream provider
    didn't supply them, never defaulted to a misleading value like `0`.
    """

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    entity_type: str
    industry: str | None = None
    match_score: float | None = None
    sentiment_score: float | None = None
