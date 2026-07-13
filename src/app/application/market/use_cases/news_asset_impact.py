from dataclasses import dataclass

from app.domain.market.entities import AssetClass
from app.domain.signals.entities import ImpactClass


@dataclass(frozen=True, slots=True)
class NewsAssetImpact:
    """How one news article bears on one instrument it affects — the per-asset row behind the
    news-detail page's affected-instrument chips (issue #57).

    Every field is read from something that actually exists; none of it is inferred:

    - `last_price`/`price_delta_pct` come from `ComputeMarketStats` (the same use case behind
      `GET /api/v1/quant/stats`), so the chip's green/red % is the identical number the asset
      page shows. `None` when the price series is unavailable or too short.
    - `sentiment_score` is the provider's per-entity sentiment for THIS instrument when it gave
      one (Marketaux does), falling back to the article-level score. `None` for plain sources.
    - `impact_class`/`confidence`/`signal_id` are the Analyst's call, and are populated **only**
      for the instrument the article's linked `Signal` actually targets — signals are generated
      per instrument (see `GenerateSignal`), so an article touching five tickers has a real
      classification for one of them. The rest carry `None` rather than a fabricated impact:
      claiming a confidence the Analyst never produced is exactly the failure mode this product
      cannot afford.
    """

    symbol: str
    name: str
    asset_class: AssetClass
    last_price: float | None = None
    price_delta_pct: float | None = None
    sentiment_score: float | None = None
    impact_class: ImpactClass | None = None
    confidence: float | None = None
    signal_id: str | None = None
