from collections.abc import Iterable, Sequence

from app.application.event_intelligence.event_relevance_vocabulary import EventRelevanceVocabulary
from app.domain.market.ports import InstrumentUniverse


def build_event_relevance_vocabulary(
    tracked_symbols: Iterable[str],
    universe: InstrumentUniverse,
    macro_keywords: Sequence[str],
    min_symbol_match_length: int,
) -> EventRelevanceVocabulary:
    """Assemble the Sentinel pre-gate's two-track match vocabulary for one scan.

    Terms come from three sources:

    * **Macro track** — every entry in `macro_keywords` (Fed, inflation, CPI, ...), always
      included verbatim.
    * **Watchlist track, symbols** — each symbol in `tracked_symbols` (the union of ALL users'
      watchlists) whose length is at least `min_symbol_match_length`. Shorter tickers are left out
      as BARE symbols because a 1-2 char ticker ("A" = Agilent, "IT" = Gartner) collides with
      ordinary words even under whole-word matching (the word-boundary anchor still fires on the
      article word "a"); they stay reachable via their company name below.
    * **Watchlist track, names** — the canonical name of each tracked symbol that resolves in the
      curated `universe` ("NVDA" -> "Nvidia"), regardless of the symbol's own length, so a headline
      that writes the company out ("Nvidia") still matches a ticker-only watchlist entry.

    Pure and synchronous: the one async `list_all_tracked_symbols()` read happens in the caller,
    which passes its result here. Returns an empty vocabulary (`is_empty`) only when every source
    is empty/blank — the caller reads that as "skip the gate", never "drop everything".
    """
    terms: list[str] = list(macro_keywords)
    for symbol in tracked_symbols:
        cleaned = symbol.strip()
        if not cleaned:
            continue
        if len(cleaned) >= min_symbol_match_length:
            terms.append(cleaned)
        instrument = universe.by_symbol(cleaned)
        if instrument is not None and instrument.name.strip():
            terms.append(instrument.name)
    return EventRelevanceVocabulary.build(terms)
