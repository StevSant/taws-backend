from dataclasses import dataclass

from app.application.instruments.enriched_instrument import EnrichedInstrument


@dataclass(frozen=True, slots=True)
class InstrumentHighlights:
    """Pre-computed "hero" groupings shown above the explorer table.

    Computed over the full filtered set (before pagination) so the leaderboards stay stable
    as the user pages through the table. Each list is already capped to a small top-N.
    """

    top_gainers: list[EnrichedInstrument]
    top_losers: list[EnrichedInstrument]
    most_volatile: list[EnrichedInstrument]
    trending: list[EnrichedInstrument]
