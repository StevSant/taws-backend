from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import LLMProvider


def get_llm_provider(container: Annotated[Container, Depends(get_container)]) -> LLMProvider:
    """FastAPI dependency resolving the configured LLMProvider from the DI container."""
    return container.get_llm_provider()
