"""Market/news application layer (issue #1): persisting fetched news and its
per-article `analysis_status`, so it survives across requests instead of being
recomputed from scratch on every `GET /api/v1/news` call.

`GET /api/v1/news` reads that persisted store directly (`ListRecentNews`) and leaves the
upstream refresh to `NewsFeedRefresher`, which runs after the response is flushed — so a
slow provider can no longer time out the radar page (taws#71).
"""

from app.application.market.news_feed_refresher import NewsFeedRefresher
from app.application.market.news_sentiment_batch import NewsSentimentBatch
from app.application.market.news_sentiment_score import NewsSentimentScore
from app.application.market.sentiment_scoring_result import SentimentScoringResult

__all__ = [
    "NewsFeedRefresher",
    "NewsSentimentBatch",
    "NewsSentimentScore",
    "SentimentScoringResult",
]
