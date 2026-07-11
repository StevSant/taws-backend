from pydantic import BaseModel, Field


class GenerateSignalRequest(BaseModel):
    """Request payload for `POST /api/v1/signals/generate`."""

    instrument_symbol: str = Field(..., min_length=1, max_length=20)
    # BCP-47-ish locale tag (e.g. "en", "es", "es-MX") the Analyst's reasoning/evidence
    # text should be written in. Falls back to `Settings.default_locale` when omitted.
    locale: str | None = Field(default=None, min_length=2, max_length=35)
