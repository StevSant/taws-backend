from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.infrastructure.telegram import ImpactCommandHandler


def get_impact_command_handler(
    container: Annotated[Container, Depends(get_container)],
) -> ImpactCommandHandler | None:
    """FastAPI dependency resolving the cached `/impact` command handler, or `None`
    when Telegram isn't configured — same pattern as `get_briefing_command_handler`."""
    return container.get_impact_command_handler()
