from dataclasses import dataclass

from app.domain.macro.entities.impact_magnitude import ImpactMagnitude
from app.domain.market.entities import AssetClass
from app.domain.signals.entities import ImpactClass


@dataclass(frozen=True, slots=True)
class MacroAssetClassImpact:
    """One asset class's tagged impact from a `MacroEventInterpretation`.

    `direction` reuses `ImpactClass` (`domain/signals`) — same positive/negative/
    neutral/uncertain vocabulary the Analyst pipeline and `domain/scenario`'s
    `ScenarioAssetClassImpact` already use for "likely direction of impact", rather
    than inventing a third direction enum. `magnitude` is `domain/macro`'s own
    `ImpactMagnitude` (see that file's docstring for why it isn't `ScenarioMagnitude`).
    `rationale` must be grounded strictly in the real FRED/VIX figures the Macro
    Analyst was given — never a free-floating LLM claim (see
    `application/macro/use_cases/interpret_macro_event.py`).
    """

    asset_class: AssetClass
    direction: ImpactClass
    magnitude: ImpactMagnitude
    rationale: str
