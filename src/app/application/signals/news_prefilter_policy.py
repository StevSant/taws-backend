from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewsPrefilterPolicy:
    """Every tunable of the Analyst pre-filter's gate, in one injectable value object (issue #26).

    `AnalyzePendingNews._prefilter` decides, without spending an LLM call, whether a pending
    news item is worth classifying. Issue #3 made that decision on symbol-relevance alone;
    this policy adds the materiality dimension it was missing, so the gate asks both "is this
    about one of our instruments?" *and* "is this important enough to be worth a token?".

    The gate score is a weighted blend, both components in `[0, 1]`:

        score = (relevance_weight * relevance + materiality_weight * materiality)
                / (relevance_weight + materiality_weight)

    and the item is kept when `score >= skip_threshold`. Because materiality is scored
    independently of ticker matching, a materially-important article that never spells out a
    watchlist ticker (the motivating case: a macro story linked to a country ETF by name, not
    by symbol) can still clear the gate — while a trivial listicle that happens to name a
    ticker can now fall below it.

    Every field is populated from `Settings` (`news_*` keys) + `.env.example` — nothing here is
    hardcoded at a call site. Constructed once in the DI container
    (`Container.get_news_prefilter_policy`) so the HTTP endpoint and the scheduled tick can't
    drift apart on their tuning.
    """

    skip_threshold: float
    relevance_weight: float
    materiality_weight: float
    # Relevance credited to an item linked to the instrument by company/fund NAME rather than
    # by its ticker (e.g. "Apple unveils…" -> AAPL). Below 1.0 because a name match is weaker
    # evidence than an explicit ticker, but far above the 0.0 such items used to score.
    name_match_score: float
    # Market-moving event terms; the share of these found in title+summary is the materiality
    # score's main component.
    materiality_keywords: tuple[str, ...]
    # Publishers whose coverage is, on its own, evidence that an event matters.
    materiality_high_impact_sources: tuple[str, ...]
    materiality_keyword_weight: float
    materiality_source_weight: float
    materiality_sentiment_weight: float
    materiality_recency_weight: float
    materiality_recency_half_life_hours: float
    # Keyword hits at or above this count saturate the keyword component at 1.0, so a
    # keyword-stuffed headline can't outscore a genuinely material one.
    materiality_keyword_saturation_count: int
