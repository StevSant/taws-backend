from enum import StrEnum


class NewsCategory(StrEnum):
    """What a news item is *about* — its subject matter (issue #69).

    Deliberately orthogonal to the signal-impact classification (`ImpactClass`): impact
    answers "is this good or bad for the instrument", category answers "what is it about".
    The two are computed on independent paths, so an item carries a category even when no
    `Signal` is ever generated for it — see `classify_news_category`.

    A small fixed taxonomy rather than free-form tags: a closed set can be filtered on with
    an indexable equality predicate, translated once per locale (ES/EN), and cannot drift
    into a long tail of near-duplicate labels.

    `UNCATEGORIZED` is its own honest state — the classifier looked and could not place the
    item — and must never be conflated with the *impact* bucket colloquially shown as
    "Sin clasificar" (which means "no impact classification"). An item can be confidently
    `MACRO` while carrying no impact at all, and vice versa.
    """

    MACRO = "macro"
    EARNINGS = "earnings"
    REGULATION = "regulation"
    CRYPTO = "crypto"
    MERGERS_ACQUISITIONS = "mergers_acquisitions"
    GEOPOLITICS = "geopolitics"
    COMPANY_NEWS = "company_news"
    UNCATEGORIZED = "uncategorized"
