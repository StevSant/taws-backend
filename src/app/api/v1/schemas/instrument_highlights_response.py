from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.enriched_instrument_response import EnrichedInstrumentResponse


class InstrumentHighlightsResponse(BaseModel):
    """Explorer "hero" leaderboards, computed over the full filtered set (pre-pagination)."""

    model_config = ConfigDict(from_attributes=True)

    top_gainers: list[EnrichedInstrumentResponse]
    top_losers: list[EnrichedInstrumentResponse]
    most_volatile: list[EnrichedInstrumentResponse]
    trending: list[EnrichedInstrumentResponse]
