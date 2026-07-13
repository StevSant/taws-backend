from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.agents.ports import LLMProvider


def get_reasoning_llm_provider(
    container: Annotated[Container, Depends(get_container)],
) -> LLMProvider:
    """FastAPI dependency resolving the REASONING-tier `LLMProvider` (issue #28).

    For the multi-step analytical endpoints — watchlist briefing composition is the only one
    that resolves the port directly today (the signal/news pipelines resolve whole use cases
    from the container instead, which pick their own tier).
    """
    return container.get_reasoning_llm_provider()
