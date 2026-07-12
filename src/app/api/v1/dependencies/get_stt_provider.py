from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import STTProvider


def get_stt_provider(
    container: Annotated[Container, Depends(get_container)],
) -> STTProvider | None:
    """FastAPI dependency resolving the configured STTProvider from the DI container.

    Returns `None` when STT isn't enabled+keyed (see `Container.get_stt_provider`); the
    `/chat/transcribe` endpoint turns that into a 503.
    """
    return container.get_stt_provider()
