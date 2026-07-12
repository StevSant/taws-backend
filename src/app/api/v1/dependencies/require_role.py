from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.v1.dependencies.require_current_user import require_current_user
from app.api.v1.schemas import CurrentUser
from app.domain.auth.entities import UserRole


def require_role(*allowed: UserRole) -> Callable[[CurrentUser], CurrentUser]:
    """Build a FastAPI dependency that admits only callers whose role is in `allowed`.

    The returned dependency resolves the caller via `require_current_user` FIRST, so an
    anonymous/invalid caller is rejected there with 401 BEFORE any role check runs — an
    unauthenticated request is never downgraded to a 403. Once authenticated, a caller
    whose `role` is not in `allowed` gets a 403. The allowed set is frozen once at
    factory time so the membership test can't be mutated per-request.
    """
    allowed_roles = frozenset(allowed)

    def _dependency(
        current_user: Annotated[CurrentUser, Depends(require_current_user)],
    ) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this action",
            )
        return current_user

    return _dependency


# Pre-bound gate for the compliance-only review write endpoints.
require_compliance = require_role(UserRole.COMPLIANCE)
