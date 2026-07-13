import re

# Corporate-form and vehicle-type boilerplate that carries no instrument-identifying signal:
# "Inc"/"Corp"/"ETF"/"Fund" appear in hundreds of names, so matching on them would link (or
# score) essentially every article against essentially every instrument. Linguistic constants,
# not tunables — deliberately not in `Settings`.
_NAME_STOPWORDS = frozenset(
    {
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
)

_MIN_TOKEN_LENGTH = 3


def extract_instrument_name_tokens(name: str) -> list[str]:
    """The lowercased, identifying words of an instrument's display name.

    Drops corporate-form boilerplate (`_NAME_STOPWORDS`) and tokens shorter than
    `_MIN_TOKEN_LENGTH`, so `"Global X MSCI Argentina ETF"` yields
    `["global", "msci", "argentina"]` and `"Apple Inc."` yields `["apple"]`.

    Shared by the two places that must agree on what "this article is about this instrument"
    means (issue #68): `link_related_symbols` (infrastructure — populates
    `NewsItem.related_symbols` for sources that don't tag instruments themselves) and
    `compute_news_relevance_score` (the pre-filter). They previously disagreed — the linker
    matched symbol OR name, the score matched symbol only — so every article linked by company
    name alone ("Apple unveils…" -> AAPL) then scored 0.0 and was silently gated out. Keeping
    the tokenizer in one place is what stops that divergence from coming back.
    """
    words = re.findall(r"[a-z0-9]+", name.lower())
    return [
        word for word in words if word not in _NAME_STOPWORDS and len(word) >= _MIN_TOKEN_LENGTH
    ]
