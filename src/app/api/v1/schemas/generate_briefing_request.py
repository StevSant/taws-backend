from pydantic import BaseModel, Field


class GenerateBriefingRequest(BaseModel):
    """Request payload for `POST /api/v1/watchlists/{id}/briefings`."""

    # BCP-47-ish locale tag (e.g. "en", "es", "es-MX") the executive summary and
    # per-instrument narratives should be written in. Falls back to
    # `Settings.default_locale` when omitted.
    locale: str | None = Field(default=None, min_length=2, max_length=35)
