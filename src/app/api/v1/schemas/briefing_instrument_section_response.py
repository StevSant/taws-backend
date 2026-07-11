from pydantic import BaseModel, ConfigDict

from app.domain.signals.entities import ImpactClass


class BriefingInstrumentSectionResponse(BaseModel):
    """Response payload for one per-instrument mini-section of a `Briefing` document."""

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    narrative: str
    impact_classes: list[ImpactClass]
    signal_ids: list[str]
    evidence_sources: list[str]
