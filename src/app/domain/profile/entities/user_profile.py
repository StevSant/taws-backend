from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class UserProfile:
    """Per-user preferences, keyed by the Supabase auth user id (issue #67).

    `preferred_locale` is the language the user picked in the UI. `None` means "no
    preference stored yet" — callers then fall back to `Settings.default_locale` rather
    than assuming a language (see `application/profile/use_cases/resolve_locale.py`).
    """

    user_id: str
    preferred_locale: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
