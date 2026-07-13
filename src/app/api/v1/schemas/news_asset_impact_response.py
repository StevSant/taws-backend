from pydantic import BaseModel, ConfigDict

from app.domain.market.entities import AssetClass
from app.domain.signals.entities import ImpactClass


class NewsAssetImpactResponse(BaseModel):
    """Response payload for one entry in `NewsDetailResponse.affected_instruments` (issue #57).

    Backs the news-detail page's affected-instrument chips: `last_price`/`price_delta_pct` are
    what makes a chip actionable (price + green/red % change) and `symbol` is what it links to
    (`radar/:symbol`), while `impact_class`/`confidence` are the Analyst's per-asset call.

    Every field is nullable for a reason, never defaulted: `impact_class`/`confidence` are
    present only for the instrument the article's linked signal actually targets (signals are
    per-instrument), and `sentiment_score` only for providers that score entities. See
    `application.market.NewsAssetImpact` for why none of them is synthesized.
    """

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    asset_class: AssetClass
    last_price: float | None = None
    price_delta_pct: float | None = None
    sentiment_score: float | None = None
    impact_class: ImpactClass | None = None
    confidence: float | None = None
    signal_id: str | None = None
