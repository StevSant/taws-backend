import re
import unicodedata

from app.domain.market.entities import NewsCategory, NewsItem

# Keyword rules per topical category. These are classification *logic*, not deployment
# configuration — there is nothing an operator would tune per environment — so they live
# next to the classifier rather than in `Settings`, the same way
# `compute_news_relevance_score`'s matching rules do.
#
# Both languages are covered because upstream providers mix English and Spanish outlets
# (`RssNewsProvider` in particular) and the classifier runs on the raw upstream text,
# before any locale-aware blurb is generated.
_CATEGORY_KEYWORDS: dict[NewsCategory, tuple[str, ...]] = {
    NewsCategory.EARNINGS: (
        "earnings",
        "quarterly results",
        "full-year results",
        "eps",
        "earnings per share",
        "revenue",
        "profit",
        "guidance",
        "outlook raised",
        "outlook cut",
        "beats estimates",
        "misses estimates",
        "resultados",
        "beneficios",
        "ingresos",
        "ganancias",
    ),
    NewsCategory.MERGERS_ACQUISITIONS: (
        "merger",
        "acquisition",
        "acquire",
        "acquires",
        "takeover",
        "buyout",
        "buys stake",
        "spin-off",
        "spinoff",
        "divestiture",
        "tender offer",
        "fusion",
        "fusiona",
        "adquisicion",
        "adquiere",
        "opa",
    ),
    NewsCategory.REGULATION: (
        "regulator",
        "regulators",
        "regulation",
        "regulatory",
        "antitrust",
        "lawsuit",
        "sues",
        "settlement",
        "fine",
        "fined",
        "penalty",
        "probe",
        "investigation",
        "subpoena",
        "compliance",
        "court",
        "ruling",
        "judge",
        "sec filing",
        "regulacion",
        "regulador",
        "demanda",
        "multa",
        "sancion",
    ),
    NewsCategory.CRYPTO: (
        "bitcoin",
        "ethereum",
        "crypto",
        "cryptocurrency",
        "blockchain",
        "stablecoin",
        "altcoin",
        "defi",
        "token",
        "mining rig",
        "halving",
        "cripto",
        "criptomoneda",
    ),
    NewsCategory.GEOPOLITICS: (
        "war",
        "invasion",
        "sanctions",
        "tariff",
        "tariffs",
        "trade war",
        "embargo",
        "election",
        "geopolitical",
        "military",
        "ceasefire",
        "opec",
        "guerra",
        "sanciones",
        "arancel",
        "aranceles",
        "elecciones",
    ),
    NewsCategory.MACRO: (
        "inflation",
        "cpi",
        "ppi",
        "federal reserve",
        "the fed",
        "fomc",
        "interest rate",
        "interest rates",
        "rate cut",
        "rate hike",
        "gdp",
        "unemployment",
        "jobs report",
        "nonfarm payrolls",
        "central bank",
        "ecb",
        "recession",
        "pmi",
        "yield curve",
        "treasury yields",
        "inflacion",
        "tipos de interes",
        "banco central",
        "desempleo",
        "recesion",
    ),
}

# Tie-break order when two categories score equally: the more specific, more actionable
# topic wins. A "Fed fines a bank" item is more usefully filed under Regulation than Macro.
_PRIORITY: tuple[NewsCategory, ...] = (
    NewsCategory.EARNINGS,
    NewsCategory.MERGERS_ACQUISITIONS,
    NewsCategory.REGULATION,
    NewsCategory.CRYPTO,
    NewsCategory.GEOPOLITICS,
    NewsCategory.MACRO,
)

# A headline is a far stronger topical signal than a body summary, which often trails
# boilerplate ("...shares fell. Read more about earnings season.").
_TITLE_WEIGHT = 2
_SUMMARY_WEIGHT = 1


def classify_news_category(item: NewsItem) -> NewsCategory:
    """Assign a topical category to `item` — what the article is *about* (issue #69).

    Deliberately orthogonal to the signal-impact path: this is a pure, non-LLM keyword
    scorer, so every ingested item gets a category even when no `Signal` is ever generated
    for it, at zero API cost and zero added latency on `GET /api/v1/news`. See
    `compute_news_relevance_score` for the same "cheap rules before/instead of an LLM call"
    shape.

    Scores each category by weighted whole-word keyword hits across the title and summary,
    and returns the highest scorer (ties broken by `_PRIORITY`). An item with no topical
    hits at all falls back to `COMPANY_NEWS` when it is linked to at least one instrument —
    it is, by construction, news about that company — and to `UNCATEGORIZED` otherwise.

    `UNCATEGORIZED` is its own honest state ("looked, could not place it") and must not be
    conflated with the *impact* bucket of the same colloquial name: an item can be
    confidently categorized as `MACRO` while carrying no impact classification at all, and
    vice versa.
    """
    scores = {category: _score(item, keywords) for category, keywords in _CATEGORY_KEYWORDS.items()}
    best = max(_PRIORITY, key=lambda category: (scores[category], -_PRIORITY.index(category)))
    if scores[best] > 0:
        return best
    return NewsCategory.COMPANY_NEWS if item.related_symbols else NewsCategory.UNCATEGORIZED


def _score(item: NewsItem, keywords: tuple[str, ...]) -> int:
    title = _fold(item.title)
    summary = _fold(item.summary)
    return sum(
        _TITLE_WEIGHT * _contains(title, keyword) + _SUMMARY_WEIGHT * _contains(summary, keyword)
        for keyword in keywords
    )


def _fold(text: str) -> str:
    """Lowercase and strip diacritics, so the Spanish keywords can be written unaccented
    and still match real copy ("inflación" → "inflacion", "regulación" → "regulacion")."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _contains(text: str, keyword: str) -> int:
    """Whole-phrase match, so "fine" doesn't fire inside "defined" and "opa" doesn't fire
    inside "Europa" — the same `\\b`-anchored approach `compute_news_relevance_score`
    already uses for symbol matching."""
    return 1 if re.search(rf"\b{re.escape(keyword)}\b", text) else 0
