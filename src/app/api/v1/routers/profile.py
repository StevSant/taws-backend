from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_user_profile_repository, require_current_user
from app.api.v1.schemas import CurrentUser, UpdateUserProfileRequest, UserProfileResponse
from app.domain.profile.entities import UserProfile
from app.domain.profile.ports import UserProfileRepository

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
async def get_profile(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[UserProfileRepository, Depends(get_user_profile_repository)],
) -> UserProfileResponse:
    """Return the authenticated user's stored preferences (issue #67).

    Always the caller's own profile — there is no `{user_id}` path param to confuse, so no
    ownership check is needed. A user who has never saved a preference has no row yet; that
    is a 200 with `preferred_locale: null`, not a 404: "no preference stored" is a normal
    state the frontend handles by keeping its current locale.
    """
    profile = await repository.get(user.id) or UserProfile(user_id=user.id)
    return UserProfileResponse.model_validate(profile)


@router.patch("")
async def update_profile(
    payload: UpdateUserProfileRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[UserProfileRepository, Depends(get_user_profile_repository)],
) -> UserProfileResponse:
    """Persist the authenticated user's preferred locale, creating the profile row if needed.

    This is what makes the language choice durable across devices: `ResolveLocale` reads it
    back on every chat turn and every AI narrative request that doesn't carry an explicit
    `locale` (see `application/profile/use_cases/resolve_locale.py`).
    """
    profile = await repository.set_preferred_locale(user.id, payload.preferred_locale)
    return UserProfileResponse.model_validate(profile)
