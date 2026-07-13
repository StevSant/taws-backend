from typing import Annotated

from fastapi import Depends

from app.application.instruments.use_cases import RegisterInstrument
from app.core.di import Container, get_container


def get_register_instrument_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> RegisterInstrument:
    """FastAPI dependency resolving the cached RegisterInstrument use case from the DI container."""
    return container.get_register_instrument_use_case()
