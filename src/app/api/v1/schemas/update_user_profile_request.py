from pydantic import BaseModel, Field


class UpdateUserProfileRequest(BaseModel):
    """Request payload for `PATCH /api/v1/profile` (issue #67).

    `preferred_locale` is a BCP-47-ish tag (e.g. "en", "es", "es-MX") — same bounds as the
    `locale` field on the signal/briefing/scenario request schemas. `null` clears the
    preference, sending the user back to `Settings.default_locale`.
    """

    preferred_locale: str | None = Field(default=None, min_length=2, max_length=35)
