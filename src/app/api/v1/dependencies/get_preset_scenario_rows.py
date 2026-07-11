from typing import Annotated, Any

from fastapi import Depends

from app.core.di import Container, get_container


def get_preset_scenario_rows(
    container: Annotated[Container, Depends(get_container)],
) -> list[dict[str, Any]]:
    """FastAPI dependency resolving the curated preset scenario rows from the DI container."""
    return container.get_preset_scenario_rows()
