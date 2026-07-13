from dataclasses import dataclass, field
from enum import StrEnum


class ScenarioAgentId(StrEnum):
    ANALYST = "analyst"
    QUANT = "quant"
    MACRO = "macro"
    SENTIMENT = "sentiment"
    CONSEQUENCE = "consequence"
    ADVISOR = "advisor"


class ScenarioContributionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class ScenarioAgentContribution:
    """One grounded specialist perspective produced by the scenario agent panel."""

    agent_id: ScenarioAgentId
    status: ScenarioContributionStatus
    thesis: str = ""
    confidence: float = 0.0
    key_findings: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    recommendation: str = ""
    uncertainty: str = ""
    failure_reason: str | None = None


@dataclass(slots=True)
class ScenarioConsensus:
    """Midas' synthesis of specialist perspectives; it is not a vote."""

    summary: str = ""
    conclusion: str = ""
    agreements: list[str] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    confidence: float = 0.0
