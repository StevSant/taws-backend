import re

from app.domain.market.entities import Instrument

_NAME_STOPWORDS = {
    "inc",
    "corp",
    "corporation",
    "co",
    "ltd",
    "plc",
    "group",
    "holdings",
    "company",
    "etf",
    "fund",
    "trust",
    "the",
    "class",
}


def link_related_symbols(text: str, instruments: list[Instrument]) -> list[str]:
    """Naively match instrument symbols/names as whole words in `text`.

    Case-insensitive. Used to backfill `NewsItem.related_symbols` for sources
    that don't tag instruments themselves (NewsAPI, Finnhub, RSS feeds).
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
    words = re.findall(r"[a-z0-9]+", name.lower())
    significant_words = [word for word in words if word not in _NAME_STOPWORDS and len(word) > 2]
    return any(_mentions_word(lowered_text, word) for word in significant_words)
