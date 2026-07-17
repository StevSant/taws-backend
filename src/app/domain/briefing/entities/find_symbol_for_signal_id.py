from app.domain.briefing.entities.briefing_instrument_section import BriefingInstrumentSection


def find_symbol_for_signal_id(
    sections: list[BriefingInstrumentSection], signal_id: str
) -> str | None:
    """Return the symbol of the breakdown section that lists `signal_id`, else `None`.

    Retention (`SignalRepository.prune_for_instrument`) deletes signal rows while
    briefings keep referencing their ids, so a dangling id's only surviving trace
    of *which instrument it belonged to* is the briefing's own
    `instrument_breakdown` — each section records the `signal_ids` it was grounded
    in. Shared by the API's linked-signal fallback mapper and the export
    enrichment, so the "which section owns this id" rule lives in exactly one place.
    """
    for section in sections:
        if signal_id in section.signal_ids:
            return section.symbol
    return None
