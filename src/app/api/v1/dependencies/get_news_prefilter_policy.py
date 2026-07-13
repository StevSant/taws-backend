from typing import Annotated

from fastapi import Depends

from app.application.signals import NewsPrefilterPolicy
from app.core.di import Container, get_container


def get_news_prefilter_policy(
    container: Annotated[Container, Depends(get_container)],
) -> NewsPrefilterPolicy:
    """FastAPI dependency resolving the Analyst pre-filter's gate tuning (issue #26).

    Same policy object the scheduled analysis tick uses, so the endpoint and the background
    job can never disagree about what gets classified.
    """
    return container.get_news_prefilter_policy()
