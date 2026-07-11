from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.notification.ports import EmailSender


def get_email_sender(
    container: Annotated[Container, Depends(get_container)],
) -> EmailSender:
    """FastAPI dependency resolving the configured EmailSender from the DI container."""
    return container.get_email_sender()
