from pydantic import BaseModel, Field

from app.domain.market.entities import AssetClass
from app.domain.signals.entities import ImpactClass


class ScenarioAssetClassSynthesisDraft(BaseModel):
    """One asset class's impact call the Synthesis step's model proposes.

    Deliberately does NOT include an `evidence` field: the model never chooses or
    formats evidence (same discipline `SignalClassification` uses — it only returns
    `reasoning`, never a `Signal.evidence` list). `SynthesizeScenarioResult` assembles
    the real evidence list deterministically from `ScenarioContext`/quant results plus
    exactly one `[razonamiento]`-tagged item built from `reasoning` below — see that use
    case's `_build_impact_map`.
    """

    asset_class: AssetClass = Field(description="Which asset class this impact call is for.")
    direction: ImpactClass = Field(
        description="The likely direction of this scenario's impact on this asset class."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in this impact call, from 0.0 to 1.0."
    )
    reasoning: str = Field(
        description=(
            "One or two sentences of interpretive reasoning for this direction/confidence, "
            "grounded strictly in the provided context, causal chain, and quant stats — "
            "never facts outside them. Becomes this impact's [razonamiento] evidence item."
        )
    )
