from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.market.ports import MacroDataProvider


def get_macro_data_provider(
    container: Annotated[Container, Depends(get_container)],
) -> MacroDataProvider:
    """FastAPI dependency resolving the configured MacroDataProvider from the DI container."""
    return container.get_macro_data_provider()
