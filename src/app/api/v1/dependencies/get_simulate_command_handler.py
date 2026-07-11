from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.infrastructure.telegram import SimulateCommandHandler


def get_simulate_command_handler(
    container: Annotated[Container, Depends(get_container)],
) -> SimulateCommandHandler | None:
    """FastAPI dependency resolving the cached `/simular <text>` command handler, or
    `None` when Telegram isn't configured (issue #19). See
    `Container.get_simulate_command_handler`."""
    return container.get_simulate_command_handler()
