from typing import Annotated

from fastapi import Depends

from app.application.sentiment.use_cases.get_market_pulse import GetMarketPulse
from app.core.config import get_settings
from app.core.di import Container, get_container
from app.infrastructure.sentiment.cnn_fear_greed_provider import CnnFearGreedProvider


def get_market_pulse_use_case(
    _container: Annotated[Container, Depends(get_container)],
) -> GetMarketPulse:
    settings = get_settings()
    return GetMarketPulse(
        cnn_provider=CnnFearGreedProvider(timeout_seconds=settings.alternative_me_timeout_seconds)
    )
