from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.notes.ports import NoteTargetResolver


def get_note_target_resolver(
    container: Annotated[Container, Depends(get_container)],
) -> NoteTargetResolver:
    """FastAPI dependency resolving the configured NoteTargetResolver from the container."""
    return container.get_note_target_resolver()
