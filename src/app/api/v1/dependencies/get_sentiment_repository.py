from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.sentiment.ports import SentimentRepository


def get_sentiment_repository(
    container: Annotated[Container, Depends(get_container)],
) -> SentimentRepository:
    """FastAPI dependency resolving the configured SentimentRepository (issue #29)."""
    return container.get_sentiment_repository()
