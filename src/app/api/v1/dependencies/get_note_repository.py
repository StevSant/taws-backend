from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.notes.ports import NoteRepository


def get_note_repository(
    container: Annotated[Container, Depends(get_container)],
) -> NoteRepository:
    """FastAPI dependency resolving the configured NoteRepository from the DI container."""
    return container.get_note_repository()
