from typing import Annotated

from fastapi import Depends

from app.application.event_intelligence.use_cases import ProcessIncomingEvent
from app.core.di import Container, get_container


def get_process_incoming_event_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> ProcessIncomingEvent:
    """FastAPI dependency resolving the cached `ProcessIncomingEvent` use case."""
    return container.get_process_incoming_event_use_case()
