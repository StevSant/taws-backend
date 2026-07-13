from typing import Annotated

from fastapi import Depends

from app.application.profile.use_cases import ResolveLocale
from app.core.di import Container, get_container


def get_resolve_locale_use_case(
    container: Annotated[Container, Depends(get_container)],
) -> ResolveLocale:
    """FastAPI dependency resolving the `ResolveLocale` use case (issue #67).

    Injected by every router that produces AI narrative for an authenticated caller, so
    "what language do we answer in" is decided in exactly one place.
    """
    return container.get_resolve_locale_use_case()
