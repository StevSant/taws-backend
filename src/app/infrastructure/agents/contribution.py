from typing import Literal

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
    stance: Literal["bull", "bear", "neutral"] = "neutral"
    """This specialist's own directional read on the question — `bull` (constructive), `bear`
    (cautious/negative), or an honest `neutral`. Self-reported and surfaced in the multi-specialist
    UI panel. Defaults to `neutral` so a model that omits it never crashes the graph, and so a
    specialist is never forced onto a side it doesn't hold."""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    """How confident this specialist is in its own read, on a 0.0–1.0 scale. Defaults to 0.0 (no
    confidence expressed) so omission is safe; a low value is an honest signal, not a failure."""
    headline: str = ""
    """A short (≤ ~80 char) plain-language takeaway for this contribution, shown in the
    multi-specialist UI panel. Defaults to empty so omission never crashes the graph."""
