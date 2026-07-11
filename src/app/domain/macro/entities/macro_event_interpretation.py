from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.macro.entities.macro_asset_class_impact import MacroAssetClassImpact
from app.domain.market.entities import MacroObservation, VolatilityRegime


@dataclass(slots=True)
class MacroEventInterpretation:
    """The Macro Analyst's produced output for one macro event (issue #21).

    Written by the Macro Analyst. `event_description` is the user-supplied event being
    interpreted (rate decision, CPI print, Fed statement, ...), or a generic label when
    none was given (see `InterpretMacroEvent.execute`'s default). `rates`/`cpi`/
    `volatility_regime` are the real `MacroDataProvider` figures (issue #15's FRED/VIX
    adapter) the interpretation was grounded in — never free-floating LLM claims.
    `asset_class_impacts` tags every asset class this event plausibly affects and how.
    No trading/execution fields exist; `disclaimer` is the same product invariant every
    other specialist output carries.
    """

    id: str
    event_description: str
    rates: MacroObservation
    cpi: MacroObservation
    volatility_regime: VolatilityRegime
    asset_class_impacts: list[MacroAssetClassImpact]
    disclaimer: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
