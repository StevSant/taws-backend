from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.infrastructure.telegram import EventCallbackHandler


def get_event_callback_handler(
    container: Annotated[Container, Depends(get_container)],
) -> EventCallbackHandler | None:
    """FastAPI dependency resolving the cached `EventCallbackHandler` from the DI container.

    `None` when `TELEGRAM_BOT_TOKEN` is unset — same `None`-gate as every other Telegram
    dependency here, so the webhook degrades instead of 500-ing when unconfigured.
    """
    return container.get_event_callback_handler()
