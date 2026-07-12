from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.enriched_instrument_response import EnrichedInstrumentResponse
from app.api.v1.schemas.instrument_highlights_response import InstrumentHighlightsResponse


class InstrumentPageResponse(BaseModel):
    """Response payload for `GET /api/v1/instruments/enriched`: one page + highlights.

    `total` counts the full filtered set (before pagination) so the client can render page
    controls; `highlights` is derived from that same full set, not just `items`.
    """

    model_config = ConfigDict(from_attributes=True)

    items: list[EnrichedInstrumentResponse]
    total: int
    page: int
    page_size: int
    highlights: InstrumentHighlightsResponse
