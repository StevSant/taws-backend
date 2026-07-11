from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.scenario.ports import ScenarioRepository


def get_scenario_repository(
    container: Annotated[Container, Depends(get_container)],
) -> ScenarioRepository:
    """FastAPI dependency resolving the configured ScenarioRepository from the DI container."""
    return container.get_scenario_repository()
