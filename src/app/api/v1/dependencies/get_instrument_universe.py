from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.market.ports import InstrumentUniverse


def get_instrument_universe(
    container: Annotated[Container, Depends(get_container)],
) -> InstrumentUniverse:
    """FastAPI dependency resolving the configured InstrumentUniverse from the DI container."""
    return container.get_instrument_universe()
