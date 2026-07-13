from typing import Annotated

from fastapi import Depends

from app.application.signals.use_cases import GenerateSignal
from app.core.di import Container, get_container


def get_generate_signal_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> GenerateSignal:
    """FastAPI dependency resolving the freshness-gated Analyst pipeline (issues #28/#29).

    The signals router used to hand-assemble `GenerateSignal` from seven `Depends(...)` ports.
    That was fine while the pipeline's only config was a source floor, but it now also carries
    a freshness policy, a retention count, a retry policy, and a model tier — settings the
    scheduled job reads too. Resolving the whole use case from the container keeps those in one
    place instead of duplicated across every surface that runs the pipeline.
    """
    return container.get_generate_signal_use_case()
