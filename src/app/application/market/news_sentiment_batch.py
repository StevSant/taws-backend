from pydantic import BaseModel, Field

from app.application.market.news_sentiment_score import NewsSentimentScore


class NewsSentimentBatch(BaseModel):
    """Structured-output schema for scoring a WHOLE chunk of articles in one LLM call.

    Batched deliberately. A per-article call would be the obvious shape, but the corpus this
    has to fill is ~2.3k rows and grows with every ingest tick; one call per headline would
    make the backfill's cost scale with the archive rather than with the work. Headlines are
    short and independent, so a chunk of them fits comfortably in one request — the model just
    returns one `NewsSentimentScore` per article, addressed by `index`.

    Mirrors `SentimentClassification`'s role for the per-INSTRUMENT tone pipeline
    (`application/sentiment/sentiment_classification.py`); this is the per-ARTICLE one. The two
    are different things and it matters: the instrument reading answers "how is the coverage of
    AAPL?", while this answers "is THIS article good or bad news?" — which is what
    `news_items.sentiment_score` (and the UI's Positivo/Negativo/Neutral filter) actually means.
    """

    scores: list[NewsSentimentScore] = Field(
        description=(
            "Exactly one entry per article you were given, in any order. Never invent an "
            "index that was not in the list, and never return two entries for one index."
        )
    )
