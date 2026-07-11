from typing import Annotated

from fastapi import Depends

from app.application.watchdog import AlertedSignalTracker
from app.core.di import Container, get_container


def get_alerted_signal_tracker(
    container: Annotated[Container, Depends(get_container)],
) -> AlertedSignalTracker:
    """FastAPI dependency resolving the process-wide AlertedSignalTracker from the DI container."""
    return container.get_alerted_signal_tracker()
