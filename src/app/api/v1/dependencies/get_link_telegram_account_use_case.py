from typing import Annotated

from fastapi import Depends

from app.application.telegram.use_cases import LinkTelegramAccount
from app.core.di import Container, get_container


def get_link_telegram_account_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> LinkTelegramAccount | None:
    """FastAPI dependency resolving the LinkTelegramAccount use case, or `None` when
    `TELEGRAM_BOT_TOKEN` isn't configured — see `Container.get_link_telegram_account_use_case`."""
    return container.get_link_telegram_account_use_case()
