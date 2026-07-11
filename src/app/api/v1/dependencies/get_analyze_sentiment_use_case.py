from typing import Annotated

from fastapi import Depends

from app.application.sentiment.use_cases import AnalyzeSentiment
from app.core.di import Container, get_container


def get_analyze_sentiment_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> AnalyzeSentiment:
    """FastAPI dependency resolving the cached `AnalyzeSentiment` use case.

    Same composed-use-case resolution shape as
    `get_generate_consequence_chain_use_case.py` — see
    `Container.get_analyze_sentiment_use_case` for why this one is cached.
    """
    return container.get_analyze_sentiment_use_case()
