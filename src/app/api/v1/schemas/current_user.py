from pydantic import BaseModel


class CurrentUser(BaseModel):
    """Authenticated (or dev-mode fake) user extracted from the Supabase JWT."""

    id: str
    email: str | None = None
