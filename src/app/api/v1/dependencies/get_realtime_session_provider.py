from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import RealtimeSessionProvider


def get_realtime_session_provider(
    container: Annotated[Container, Depends(get_container)],
) -> RealtimeSessionProvider | None:
    """FastAPI dependency resolving the Realtime session provider, or `None` when the
    feature is disabled/unconfigured — the `/chat/realtime/session` handler turns
    `None` into a 503 (see `api/v1/routers/chat.py`).
    """
    return container.get_realtime_session_provider()
