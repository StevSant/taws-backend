from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.market.ports import InstrumentMetadataProvider


def get_instrument_metadata_provider(
    container: Annotated[Container, Depends(get_container)],
) -> InstrumentMetadataProvider:
    """FastAPI dependency resolving the cached InstrumentMetadataProvider from the container."""
    return container.get_instrument_metadata_provider()
