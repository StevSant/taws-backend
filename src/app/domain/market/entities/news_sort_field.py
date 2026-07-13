from enum import StrEnum


class NewsSortField(StrEnum):
    """Sortable columns for `GET /api/v1/news/browse`.

    Each member maps 1:1 to a `news_items` column, so the DB can order on it
    directly rather than the API sorting a page in Python.
    """

    PUBLISHED_AT = "published_at"
    SOURCE = "source"
