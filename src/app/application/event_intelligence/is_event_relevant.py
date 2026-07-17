from app.application.event_intelligence.event_relevance_vocabulary import EventRelevanceVocabulary


def is_event_relevant(title: str, description: str, vocabulary: EventRelevanceVocabulary) -> bool:
    """True when a raw article's title or description hits either relevance track.

    The cheap, no-LLM pre-gate `BroadcastImportantEvents` applies before spending a Gemini
    `analyze` call: an article survives when its `title` + `description` mentions a watchlisted
    symbol or company name (the watchlist track) OR a macro keyword (the macro track) — both
    tracks live in `vocabulary`. Matching is whole-word and case-insensitive; see
    `EventRelevanceVocabulary`. An empty vocabulary matches nothing, so callers must gate on
    `vocabulary.is_empty` before treating a `False` here as "irrelevant".
    """
    return vocabulary.matches(f"{title}\n{description}")
