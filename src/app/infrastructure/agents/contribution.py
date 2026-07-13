from pydantic import BaseModel, Field

from app.infrastructure.agents.finding import Finding


class Contribution(BaseModel):
    agent: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    analysis: str | None = None
    """The contributor's full grounded response text, passed through to the synthesizer verbatim
    (bounded contributor-side) so numbers, caveats, and chart references that the typed `summary`
    and `findings` digest drops are never lost on a multi-route turn. Optional: `None` when there
    is no response text to carry. Always overwritten with the real response by the contributor —
    never LLM-filled, even though it appears in the `with_structured_output` schema."""
