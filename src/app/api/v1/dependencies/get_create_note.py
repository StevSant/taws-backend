from typing import Annotated

from fastapi import Depends

from app.application.notes.use_cases import CreateNote
from app.core.di import Container, get_container


def get_create_note(
    container: Annotated[Container, Depends(get_container)],
) -> CreateNote:
    """FastAPI dependency resolving the CreateNote use case from the container."""
    return container.get_create_note()
