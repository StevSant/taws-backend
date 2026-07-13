from pydantic import BaseModel, Field


class ScenarioAgentContributionExtraction(BaseModel):
    thesis: str = Field(description="Concise specialist thesis grounded only in supplied context.")
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[str] = Field(default_factory=list, max_length=6)
    evidence_refs: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="Short references to exact supplied facts, never invented citations.",
    )
    risks: list[str] = Field(default_factory=list, max_length=5)
    recommendation: str = Field(
        default="",
        description="Research or monitoring recommendation, not an execution instruction.",
    )
    uncertainty: str = Field(
        description="What is unknown, missing, or could invalidate this perspective."
    )
