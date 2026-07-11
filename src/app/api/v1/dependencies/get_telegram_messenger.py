from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.telegram.ports import TelegramMessenger


def get_telegram_messenger(
    container: Annotated[Container, Depends(get_container)],
) -> TelegramMessenger | None:
    """FastAPI dependency resolving the cached `TelegramMessenger`, or `None` when
    `TELEGRAM_BOT_TOKEN` isn't configured — see `Container.get_telegram_messenger`.
    Used directly by the webhook router to reply to an `UnknownCommand` (issue #19),
    which needs no other port.
    """
    return container.get_telegram_messenger()
