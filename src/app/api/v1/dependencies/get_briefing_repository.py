from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.briefing.ports import BriefingRepository


def get_briefing_repository(
    container: Annotated[Container, Depends(get_container)],
) -> BriefingRepository:
    """FastAPI dependency resolving the configured BriefingRepository from the DI container."""
    return container.get_briefing_repository()
