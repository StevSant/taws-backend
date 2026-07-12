from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import TTSProvider


def get_tts_provider(
    container: Annotated[Container, Depends(get_container)],
) -> TTSProvider | None:
    """FastAPI dependency resolving the configured TTSProvider from the DI container.

    Returns `None` when TTS isn't enabled+keyed (see `Container.get_tts_provider`); the
    `/chat/speak` endpoint turns that into a 503.
    """
    return container.get_tts_provider()
