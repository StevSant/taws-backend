from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.infrastructure.telegram import BriefingCommandHandler


def get_briefing_command_handler(
    container: Annotated[Container, Depends(get_container)],
) -> BriefingCommandHandler | None:
    """FastAPI dependency resolving the cached `/briefing` command handler, or `None`
    when Telegram isn't configured (issue #19). See
    `Container.get_briefing_command_handler`."""
    return container.get_briefing_command_handler()
