from typing import Annotated

from fastapi import Depends

from app.application.consequence.use_cases import GenerateConsequenceChain
from app.core.di import Container, get_container


def get_generate_consequence_chain_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> GenerateConsequenceChain:
    """FastAPI dependency resolving the cached `GenerateConsequenceChain` use case.

    Same composed-use-case resolution shape as `get_agent_runner.py` (resolves the fully
    wired object from `Container`, not individual ports) — see
    `Container.get_generate_consequence_chain_use_case` for why this one is cached.
    """
    return container.get_generate_consequence_chain_use_case()
