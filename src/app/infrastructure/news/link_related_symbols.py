import re

from app.application.market.use_cases import extract_instrument_name_tokens
from app.domain.market.entities import Instrument


def link_related_symbols(text: str, instruments: list[Instrument]) -> list[str]:
    """Naively match instrument symbols/names as whole words in `text`.

    Case-insensitive. Used to backfill `NewsItem.related_symbols` for sources
    that don't tag instruments themselves (NewsAPI, Finnhub, RSS feeds).

    The name half of the match uses the shared `extract_instrument_name_tokens` so the
    Analyst pre-filter's `compute_news_relevance_score` scores an article by exactly the
    rule this linker used to link it (issue #68) — see that tokenizer's docstring for the
    divergence this prevents.
    """
    lowered = text.lower()
    matched: list[str] = []
    for instrument in instruments:
        if _mentions_word(lowered, instrument.symbol) or _mentions_name(lowered, instrument.name):
            matched.append(instrument.symbol)
    return matched


def _mentions_word(lowered_text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token.lower())}\b", lowered_text) is not None


def _mentions_name(lowered_text: str, name: str) -> bool:
    return any(
        _mentions_word(lowered_text, token) for token in extract_instrument_name_tokens(name)
    )
