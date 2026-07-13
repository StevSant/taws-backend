import re

from app.application.market.use_cases import extract_instrument_name_tokens
from app.domain.market.entities import Instrument, NewsItem


def compute_news_relevance_score(
    item: NewsItem, instrument: Instrument, name_match_score: float
) -> float:
    """Cheap, non-LLM relevance score in `[0, 1]` for how much `item` is *about* `instrument`
    (issue #3's pre-filter; one of the two components of the gate — see `NewsPrefilterPolicy`).

    Three tiers, most trustworthy first:

    1. The enrichment `match_score` a provider (Marketaux) already attached to this
       instrument's `NewsEntity` — the provider's own confidence that the article is actually
       about this entity. Clamped into `[0, 1]`, since the score's upstream scale isn't
       guaranteed and the blend in `NewsPrefilterPolicy` assumes a unit range.
    2. A whole-word ticker match against title+summary — an explicit `AAPL` is unambiguous:
       1.0.
    3. A whole-word match on one of the instrument's identifying NAME tokens (issue #68):
       `name_match_score`, configured via `Settings.news_relevance_name_match_score`.

    Tier 3 is the fix for the bug behind "every item shows Sin clasificar". `related_symbols`
    is populated by `link_related_symbols`, which links on ticker OR company name — but this
    score used to check the ticker only. So "Apple unveils the new iPhone" was linked to AAPL,
    then scored 0.0 here, fell under the skip threshold, and was silently gated out without an
    LLM call. Since most headlines name the company and not the ticker, that gated out most of
    the items the linker had just linked, and they surfaced as the ambiguous "Sin clasificar"
    tag. Both sides now agree on what "about this instrument" means, via the shared
    `extract_instrument_name_tokens`.
    """
    for entity in item.entities:
        if entity.symbol.upper() == instrument.symbol.upper() and entity.match_score is not None:
            return min(max(entity.match_score, 0.0), 1.0)

    text = f"{item.title} {item.summary}".lower()
    if _mentions_word(text, instrument.symbol):
        return 1.0

    name_tokens = extract_instrument_name_tokens(instrument.name)
    if any(_mentions_word(text, token) for token in name_tokens):
        return min(max(name_match_score, 0.0), 1.0)
    return 0.0


def _mentions_word(lowered_text: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token.lower())}\b", lowered_text) is not None
