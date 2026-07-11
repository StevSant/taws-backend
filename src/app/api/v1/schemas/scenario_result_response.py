from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.consequence_chain_response import ConsequenceChainResponse
from app.api.v1.schemas.scenario_asset_class_impact_response import (
    ScenarioAssetClassImpactResponse,
)
from app.api.v1.schemas.scenario_spec_response import ScenarioSpecResponse


class ScenarioResultResponse(BaseModel):
    """Response payload for a single Scenario Simulation graph result (issue #12).

    `consequence_chain` reuses `ConsequenceChainResponse` as-is (the same schema
    `POST /api/v1/consequence-chains/generate` returns) — a `ScenarioResult` embeds the
    full causal chain produced for that run, not a reference to one.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    spec: ScenarioSpecResponse
    title: str
    narrative: str
    impact_map: list[ScenarioAssetClassImpactResponse]
    consequence_chain: ConsequenceChainResponse
    recommended_actions: list[str]
    disclaimer: str
    created_at: datetime
