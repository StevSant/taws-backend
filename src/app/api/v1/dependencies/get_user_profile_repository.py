from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.domain.profile.ports import UserProfileRepository


def get_user_profile_repository(
    container: Annotated[Container, Depends(get_container)],
) -> UserProfileRepository:
    """FastAPI dependency resolving the configured UserProfileRepository from the container."""
    return container.get_user_profile_repository()
