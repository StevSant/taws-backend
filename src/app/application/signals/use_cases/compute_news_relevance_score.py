import re

from app.domain.market.entities import Instrument, NewsItem


def compute_news_relevance_score(item: NewsItem, instrument: Instrument) -> float:
    """Cheap, non-LLM relevance score in `[0, 1]` for whether `item` is worth spending an
    LLM classification call on for `instrument` (issue #3's pre-filter).

    Prefers the enrichment `match_score` a provider (Marketaux) already attached to this
    instrument's `NewsEntity` — the provider's own confidence that the article is
    actually about this entity — when present. Falls back to a naive whole-word symbol
    match against the title/summary (1.0 if present, 0.0 otherwise) for items with no
    entity enrichment (e.g. NewsAPI, RSS, SEC EDGAR), since those sources only ever
    populate `NewsItem.related_symbols` (see `link_related_symbols.py`), not `entities`.
    """
    for entity in item.entities:
        if entity.symbol.upper() == instrument.symbol.upper() and entity.match_score is not None:
            return entity.match_score

    text = f"{item.title} {item.summary}".lower()
    matches_symbol = re.search(rf"\b{re.escape(instrument.symbol.lower())}\b", text) is not None
    return 1.0 if matches_symbol else 0.0
