import re

from pydantic import BaseModel, Field, field_validator

# Deliberately a light shape check, not full RFC 5322 validation — `pydantic.EmailStr`
# would need the `email-validator` extra, an extra dependency this endpoint doesn't
# justify pulling in just to reject malformed input a bit more precisely.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BriefingExportEmailRequest(BaseModel):
    """Request payload for `POST /api/v1/briefings/{briefing_id}/export/email`."""

    to: str = Field(..., min_length=3, max_length=254)

    @field_validator("to")
    @classmethod
    def _validate_email_shape(cls, value: str) -> str:
        stripped = value.strip()
        if not _EMAIL_PATTERN.match(stripped):
            raise ValueError("to must be a valid email address")
        return stripped
