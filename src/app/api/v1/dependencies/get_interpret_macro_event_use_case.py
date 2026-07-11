from typing import Annotated

from fastapi import Depends

from app.application.macro.use_cases import InterpretMacroEvent
from app.core.di import Container, get_container


def get_interpret_macro_event_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> InterpretMacroEvent:
    """FastAPI dependency resolving the cached `InterpretMacroEvent` use case.

    Same composed-use-case resolution shape as
    `get_generate_consequence_chain_use_case.py` — see
    `Container.get_interpret_macro_event_use_case` for why this one is cached.
    """
    return container.get_interpret_macro_event_use_case()
