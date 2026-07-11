from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.infrastructure.telegram import SignalCommandHandler


def get_signal_command_handler(
    container: Annotated[Container, Depends(get_container)],
) -> SignalCommandHandler | None:
    """FastAPI dependency resolving the cached `/signal <TICKER>` command handler, or
    `None` when Telegram isn't configured (issue #19). See
    `Container.get_signal_command_handler`."""
    return container.get_signal_command_handler()
