from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import LLMProvider


def get_fast_llm_provider(container: Annotated[Container, Depends(get_container)]) -> LLMProvider:
    """FastAPI dependency resolving the FAST-tier `LLMProvider` (issue #28).

    For structured, low-reasoning endpoints — news blurb localization is the only one that
    resolves the port directly today. Reasoning-tier endpoints must use
    `get_reasoning_llm_provider`; there is deliberately no un-suffixed `get_llm_provider`
    left to pick by accident.
    """
    return container.get_fast_llm_provider()
