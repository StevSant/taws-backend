from enum import StrEnum


class UserRole(StrEnum):
    """The closed set of caller roles the RBAC layer recognizes.

    A `StrEnum` so a member serializes/compares as its raw string value (e.g.
    `"compliance"`) and can be built straight from a JWT role claim via `UserRole(value)`.

    `MEMBER` is the deliberate DEFAULT for any authenticated caller whose role can't be
    recognized (no role claim, an unknown/forged role literal, or a non-dev caller with
    only a demo email). Defaulting to the least-privileged role means an unrecognized
    caller is BLOCKED from privileged actions rather than silently granted them.
    """

    ANALYST = "analyst"
    PORTFOLIO = "portfolio"
    COMPLIANCE = "compliance"
    MEMBER = "member"
