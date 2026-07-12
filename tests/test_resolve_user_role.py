"""Unit tests for `resolve_user_role` — JWT-payload -> `UserRole`, failing safe to MEMBER.

Precedence, verified below:
    1. `app_metadata.role` claim (Supabase's own place for app-controlled role claims)
    2. top-level `role` claim
    3. DEV-ONLY `demo_email_role_map` (email -> role), consulted ONLY when
       `dev_fallback_allowed(settings)` is True
    4. `UserRole.MEMBER` (the safe default)

THE key security regression guard: `test_demo_email_map_is_ignored_in_production`. The
demo email->role map must NEVER be consulted in a non-dev env, because the
`compliance@midas.demo` credentials ship publicly in the frontend prod bundle — if the
email fallback fired in prod, anyone self-signing-up that email would be handed COMPLIANCE
on an otherwise-valid JWT (privilege escalation). In prod the role comes ONLY from the
verified JWT claims.
"""

from typing import Any

from app.api.v1.dependencies.resolve_user_role import resolve_user_role
from app.core.config import Settings
from app.domain.auth.entities import UserRole


def _settings(*, app_env: str = "development") -> Settings:
    return Settings(app_env=app_env)


# ---- claim-based resolution (env-independent) ------------------------------------------


def test_app_metadata_role_claim_wins() -> None:
    payload: dict[str, Any] = {"app_metadata": {"role": "compliance"}}
    assert resolve_user_role(payload, _settings()) is UserRole.COMPLIANCE


def test_top_level_role_claim_is_accepted() -> None:
    payload: dict[str, Any] = {"role": "analyst"}
    assert resolve_user_role(payload, _settings()) is UserRole.ANALYST


def test_app_metadata_takes_precedence_over_top_level_role() -> None:
    payload: dict[str, Any] = {
        "app_metadata": {"role": "compliance"},
        "role": "member",
    }
    assert resolve_user_role(payload, _settings()) is UserRole.COMPLIANCE


def test_forged_string_role_falls_through_to_member() -> None:
    payload: dict[str, Any] = {"app_metadata": {"role": "superadmin"}}
    assert resolve_user_role(payload, _settings()) is UserRole.MEMBER


def test_non_string_role_claim_is_ignored() -> None:
    payload: dict[str, Any] = {"role": ["compliance"]}
    assert resolve_user_role(payload, _settings()) is UserRole.MEMBER


def test_non_dict_app_metadata_is_ignored_and_falls_through() -> None:
    payload: dict[str, Any] = {"app_metadata": "compliance", "role": "analyst"}
    # `app_metadata` is not a dict, so the top-level `role` is used instead.
    assert resolve_user_role(payload, _settings()) is UserRole.ANALYST


# ---- demo email fallback: DEV ONLY -----------------------------------------------------


def test_demo_email_map_resolves_role_in_development() -> None:
    payload: dict[str, Any] = {"email": "compliance@midas.demo"}
    assert resolve_user_role(payload, _settings(app_env="development")) is UserRole.COMPLIANCE


def test_demo_email_map_resolves_analyst_in_development() -> None:
    payload: dict[str, Any] = {"email": "analista@midas.demo"}
    assert resolve_user_role(payload, _settings(app_env="development")) is UserRole.ANALYST


def test_demo_email_map_is_ignored_in_production() -> None:
    # THE security regression guard. compliance@midas.demo ships publicly in the prod
    # frontend bundle; in prod the email must NOT grant a role — only verified JWT claims
    # can. No role claim + prod => MEMBER, never COMPLIANCE.
    payload: dict[str, Any] = {"email": "compliance@midas.demo"}
    assert resolve_user_role(payload, _settings(app_env="production")) is UserRole.MEMBER


def test_demo_email_map_is_ignored_in_staging() -> None:
    # Staging is not a dev env either — same fail-safe as production.
    payload: dict[str, Any] = {"email": "compliance@midas.demo"}
    assert resolve_user_role(payload, _settings(app_env="staging")) is UserRole.MEMBER


def test_verified_claim_beats_demo_email_even_in_dev() -> None:
    # A real claim always wins; the email fallback is only for claim-less dev tokens.
    payload: dict[str, Any] = {
        "app_metadata": {"role": "analyst"},
        "email": "compliance@midas.demo",
    }
    assert resolve_user_role(payload, _settings(app_env="development")) is UserRole.ANALYST


# ---- unknown / empty callers -----------------------------------------------------------


def test_unknown_user_defaults_to_member() -> None:
    payload: dict[str, Any] = {"email": "stranger@nowhere.io"}
    assert resolve_user_role(payload, _settings(app_env="development")) is UserRole.MEMBER


def test_empty_payload_defaults_to_member() -> None:
    assert resolve_user_role({}, _settings(app_env="development")) is UserRole.MEMBER
