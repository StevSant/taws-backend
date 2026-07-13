from pydantic import BaseModel, ConfigDict

from app.domain.scenario.entities import ScenarioAgentId, ScenarioContributionStatus


class ScenarioAgentContributionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: ScenarioAgentId
    status: ScenarioContributionStatus
    thesis: str
    confidence: float
    key_findings: list[str]
    evidence_refs: list[str]
    risks: list[str]
    recommendation: str
    uncertainty: str
    failure_reason: str | None


class ScenarioConsensusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: str
    conclusion: str
    agreements: list[str]
    disagreements: list[str]
    uncertainties: list[str]
    confidence: float
