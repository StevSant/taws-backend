"""Unit tests for the `require_role` dependency factory (RBAC gate).

`require_role(*allowed)` returns a FastAPI dependency that resolves the current user
(via `require_current_user`, so an anonymous caller is rejected there with 401 BEFORE any
role check — never downgraded to 403) and then raises `HTTPException(403)` unless the
resolved user's role is one of `allowed`. `require_compliance` is the pre-bound gate for
the compliance-only write endpoints.

These tests call the inner dependency directly with a constructed `CurrentUser`, so the
role branch is exercised in isolation from the 401/auth resolution (covered by
`test_require_current_user.py`).
"""

import pytest
from fastapi import HTTPException, status

from app.api.v1.dependencies.require_role import require_compliance, require_role
from app.api.v1.schemas import CurrentUser
from app.domain.auth.entities import UserRole


def _user(role: UserRole) -> CurrentUser:
    return CurrentUser(id="user-1", email="user@example.io", role=role)


def test_allowed_role_passes_and_returns_the_user() -> None:
    dependency = require_role(UserRole.COMPLIANCE)
    user = _user(UserRole.COMPLIANCE)
    assert dependency(user) is user


def test_disallowed_role_raises_403() -> None:
    dependency = require_role(UserRole.COMPLIANCE)
    with pytest.raises(HTTPException) as exc:
        dependency(_user(UserRole.ANALYST))
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_member_default_is_blocked() -> None:
    dependency = require_role(UserRole.COMPLIANCE)
    with pytest.raises(HTTPException) as exc:
        dependency(_user(UserRole.MEMBER))
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_multiple_allowed_roles_are_all_accepted() -> None:
    dependency = require_role(UserRole.ANALYST, UserRole.PORTFOLIO)
    analyst = _user(UserRole.ANALYST)
    portfolio = _user(UserRole.PORTFOLIO)
    assert dependency(analyst) is analyst
    assert dependency(portfolio) is portfolio


def test_role_outside_multiple_allowed_is_blocked() -> None:
    dependency = require_role(UserRole.ANALYST, UserRole.PORTFOLIO)
    with pytest.raises(HTTPException) as exc:
        dependency(_user(UserRole.COMPLIANCE))
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_require_compliance_allows_compliance() -> None:
    user = _user(UserRole.COMPLIANCE)
    assert require_compliance(user) is user


def test_require_compliance_blocks_non_compliance() -> None:
    with pytest.raises(HTTPException) as exc:
        require_compliance(_user(UserRole.PORTFOLIO))
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
