import re
from datetime import UTC, datetime

from app.application.signals.news_prefilter_policy import NewsPrefilterPolicy
from app.domain.market.entities import NewsItem


def compute_news_materiality_score(
    item: NewsItem, policy: NewsPrefilterPolicy, now: datetime
) -> float:
    """Cheap, non-LLM materiality score in `[0, 1]`: "is this news important enough to be worth
    an LLM classification call?" — asked independently of whether the article names a watchlist
    ticker (issue #26; the other component of the gate, see `NewsPrefilterPolicy`).

    The pre-filter shipped in #3 only ever asked "does this name one of our symbols?", so a
    broad macro story that moves a country ETF was dropped exactly like boilerplate, while a
    trivial listicle that happened to spell out a ticker passed and burned a token. This adds
    the missing dimension, with four signals — each normalized to `[0, 1]`, then blended with
    the policy's weights:

    - **keyword** — how many of `materiality_keywords` (market-moving event terms: rate cuts,
      guidance cuts, defaults, sanctions…) appear as whole words in title+summary, saturating
      at `materiality_keyword_saturation_count` hits so keyword stuffing can't run away with
      the score;
    - **source** — 1.0 when the publisher is one of `materiality_high_impact_sources`, whose
      choosing to cover something is itself evidence it matters;
    - **sentiment** — `|sentiment_score|` when a provider enriched the item: a strongly-toned
      article is likelier to be material than a flat one. 0.0 when absent — never defaulted to
      a misleading midpoint;
    - **recency** — exponential decay on `materiality_recency_half_life_hours`, since a
      stale story is a worse use of a token than a breaking one.

    Deliberately *not* an embedding-similarity or small-model triage pass (both were floated in
    #26): those cost a network call per item, which defeats the point of a pre-filter that
    exists to *avoid* per-item API spend. Everything here is local string/arithmetic work.

    The blend divides by the sum of the weights, so zeroing a component out via `Settings`
    reweights the rest instead of silently shrinking the score's range (which would drag every
    item under the threshold).
    """
    weights = (
        policy.materiality_keyword_weight,
        policy.materiality_source_weight,
        policy.materiality_sentiment_weight,
        policy.materiality_recency_weight,
    )
    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.0

    scores = (
        _keyword_score(item, policy),
        _source_score(item, policy),
        _sentiment_score(item),
        _recency_score(item.published_at, now, policy.materiality_recency_half_life_hours),
    )
    blended = sum(weight * score for weight, score in zip(weights, scores, strict=True))
    return min(max(blended / total_weight, 0.0), 1.0)


def _keyword_score(item: NewsItem, policy: NewsPrefilterPolicy) -> float:
    saturation = max(policy.materiality_keyword_saturation_count, 1)
    text = f"{item.title} {item.summary}".lower()
    hits = sum(1 for keyword in policy.materiality_keywords if _mentions_phrase(text, keyword))
    return min(hits / saturation, 1.0)


def _source_score(item: NewsItem, policy: NewsPrefilterPolicy) -> float:
    high_impact = {source.strip().lower() for source in policy.materiality_high_impact_sources}
    return 1.0 if item.source.strip().lower() in high_impact else 0.0


def _sentiment_score(item: NewsItem) -> float:
    if item.sentiment_score is None:
        return 0.0
    return min(abs(item.sentiment_score), 1.0)


def _recency_score(published_at: datetime, now: datetime, half_life_hours: float) -> float:
    """`0.5 ** (age / half_life)` — 1.0 at publication, 0.5 one half-life later.

    A naive `published_at` is read as UTC rather than crashing on a naive/aware comparison:
    every adapter is supposed to emit an aware timestamp, but a pre-filter must never be the
    thing that takes the analysis pipeline down if one doesn't.
    """
    if half_life_hours <= 0:
        return 0.0
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age_hours = (now - published_at).total_seconds() / 3600
    if age_hours <= 0:
        return 1.0
    return min(max(0.5 ** (age_hours / half_life_hours), 0.0), 1.0)


def _mentions_phrase(lowered_text: str, phrase: str) -> bool:
    """Whole-word match, so `"ipo"` can't fire on `"lipogenesis"`. Multi-word keywords
    (`"rate cut"`) match on any run of whitespace between their words."""
    words = [re.escape(word) for word in phrase.lower().split()]
    if not words:
        return False
    return re.search(rf"\b{r'\s+'.join(words)}\b", lowered_text) is not None
