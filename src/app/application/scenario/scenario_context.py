from dataclasses import dataclass, field

from app.application.quant.market_stats import MarketStats
from app.domain.market.entities import MacroObservation, NewsItem, VolatilityRegime
from app.domain.scenario.entities import ScenarioEvidence


@dataclass(slots=True)
class ScenarioContext:
    """Result of `GatherScenarioContext.execute(...)`: the Context gathering step's output.

    Not persisted (no repository) — a computed-on-demand value object feeding the
    Synthesis step's grounding prompt, same role as `application.quant.MarketStats` for
    the Quant pipeline. Every field degrades to `None`/empty rather than raising when its
    source fails — see `GatherScenarioContext`'s docstring.

    `market_stats`/`historical_analogs` are keyed by instrument symbol (only entries that
    succeeded) so the Synthesis step can bucket them by asset class via
    `InstrumentUniverse.by_symbol(...).asset_class` without re-fetching anything.
    """

    market_stats: dict[str, MarketStats] = field(default_factory=dict)
    news_items: list[NewsItem] = field(default_factory=list)
    macro_rates: MacroObservation | None = None
    macro_cpi: MacroObservation | None = None
    volatility_regime: VolatilityRegime | None = None
    historical_analogs: dict[str, list[ScenarioEvidence]] = field(default_factory=dict)
