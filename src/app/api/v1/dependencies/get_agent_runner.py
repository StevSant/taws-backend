from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import AgentRunner


def get_agent_runner(container: Annotated[Container, Depends(get_container)]) -> AgentRunner:
    """FastAPI dependency resolving the configured AgentRunner from the DI container."""
    return container.get_agent_runner()
