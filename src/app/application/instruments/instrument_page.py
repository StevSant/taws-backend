from dataclasses import dataclass

from app.application.instruments.enriched_instrument import EnrichedInstrument
from app.application.instruments.instrument_highlights import InstrumentHighlights


@dataclass(frozen=True, slots=True)
class InstrumentPage:
    """One page of enriched instrument rows plus the explorer highlight groupings.

    `total` is the size of the full filtered set (before pagination), so the frontend can
    render page controls. `highlights` is computed over that same full set, not just `items`.
    """

    items: list[EnrichedInstrument]
    total: int
    page: int
    page_size: int
    highlights: InstrumentHighlights
