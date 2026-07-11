from pydantic import BaseModel, Field

from app.domain.macro.entities import ImpactMagnitude
from app.domain.market.entities import AssetClass
from app.domain.signals.entities import ImpactClass


class MacroAssetClassImpactDraft(BaseModel):
    """One asset class's impact call the Macro Analyst's model proposes.

    Mirrors `ScenarioAssetClassSynthesisDraft`'s role for the Scenario Synthesis step
    (`application/scenario/scenario_asset_class_synthesis_draft.py`) — the model tags
    direction + magnitude and gives its reasoning, grounded strictly in the real FRED/
    VIX figures it was given; it never invents macro numbers of its own.
    """

    asset_class: AssetClass = Field(description="Which asset class this impact call is for.")
    direction: ImpactClass = Field(
        description="The likely direction of this macro event's impact on this asset class."
    )
    magnitude: ImpactMagnitude = Field(
        description="How large this asset class's impact is expected to be."
    )
    rationale: str = Field(
        description=(
            "One or two sentences grounding the direction/magnitude strictly in the "
            "provided rates/CPI/volatility figures and event description — never facts "
            "outside them."
        )
    )
