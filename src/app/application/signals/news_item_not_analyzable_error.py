from app.domain.market.entities import NewsSkipReason


class NewsItemNotAnalyzableError(RuntimeError):
    """Raised when a news item exists but cannot produce a `Signal` (issue #27).

    Carries the `NewsSkipReason` that has just been persisted onto the item, so
    `POST /api/v1/news/{news_id}/analyze` can hand the frontend a machine-readable reason
    ("no linked instrument", "insufficient evidence", "compliance blocked") to render, rather
    than an opaque failure. The manual trigger bypasses the *pre-filter* — it does not bypass
    the evidence floor or the compliance gate, which are correctness guarantees, not cost
    optimizations.
    """

    def __init__(self, news_id: str, skip_reason: NewsSkipReason, message: str) -> None:
        super().__init__(message)
        self.news_id = news_id
        self.skip_reason = skip_reason
