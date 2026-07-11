from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.notification.ports import NotificationChannel


def get_notification_channel(
    container: Annotated[Container, Depends(get_container)],
) -> NotificationChannel:
    """FastAPI dependency resolving the configured NotificationChannel from the DI container."""
    return container.get_notification_channel()
