from pydantic import BaseModel

from app.domain.auth.entities import UserRole


class CurrentUser(BaseModel):
    """Authenticated (or dev-mode fake) user extracted from the Supabase JWT."""

    id: str
    email: str | None = None
    role: UserRole = UserRole.MEMBER
