from pydantic import BaseModel, ConfigDict


class UserProfileResponse(BaseModel):
    """Response payload for the authenticated user's profile (issue #67).

    `preferred_locale` is `null` when the user has never picked a language — the frontend
    then keeps whatever locale it already had (its own `es` default, or the localStorage
    choice made while anonymous) instead of forcing one.
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    preferred_locale: str | None = None
