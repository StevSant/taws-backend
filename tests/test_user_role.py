"""Unit tests for the `UserRole` domain enum.

`UserRole` is the closed set of caller roles the RBAC layer recognizes. It is a
`StrEnum` so it serializes/compares as its string value (e.g. `"compliance"`) and can be
constructed straight from a raw JWT claim string. `MEMBER` is the deliberate default for
any authenticated caller whose role can't be recognized, so unknown callers are blocked
from privileged actions rather than silently granted them.
"""

from enum import StrEnum

from app.domain.auth.entities import UserRole


def test_user_role_has_the_four_product_roles() -> None:
    assert {role.value for role in UserRole} == {
        "analyst",
        "portfolio",
        "compliance",
        "member",
    }


def test_user_role_is_a_str_enum() -> None:
    assert issubclass(UserRole, StrEnum)
    # StrEnum members compare equal to and behave as their string value.
    assert UserRole.COMPLIANCE == "compliance"
    assert f"{UserRole.ANALYST}" == "analyst"


def test_user_role_is_constructible_from_string() -> None:
    assert UserRole("analyst") is UserRole.ANALYST
    assert UserRole("portfolio") is UserRole.PORTFOLIO
    assert UserRole("compliance") is UserRole.COMPLIANCE
    assert UserRole("member") is UserRole.MEMBER


def test_user_role_is_re_exported_from_package_root() -> None:
    from app.domain.auth import UserRole as RootUserRole

    assert RootUserRole is UserRole
