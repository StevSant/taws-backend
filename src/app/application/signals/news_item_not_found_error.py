class NewsItemNotFoundError(LookupError):
    """Raised when a use case is asked to act on a `news_items` id that doesn't exist.

    `ForceAnalyzeNewsItem` (issue #27) raises this so `POST /api/v1/news/{news_id}/analyze` can
    answer 404 without the application layer knowing what an HTTP status code is.
    """

    def __init__(self, news_id: str) -> None:
        super().__init__(f"No news item found with id {news_id!r}")
        self.news_id = news_id
