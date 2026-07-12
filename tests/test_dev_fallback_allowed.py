"""Unit tests for `dev_fallback_allowed` — the pure predicate that decides whether the
fake `DEV_FALLBACK_USER` may stand in for a real authenticated user when no
`SUPABASE_JWT_SECRET` is configured.

Fail-closed contract: the fallback is allowed ONLY in a development/test/local env; every
other value (production, staging, anything unrecognized) must be rejected.
"""

import pytest

from app.api.v1.dependencies.dev_fallback_allowed import DEV_ENV_NAMES, dev_fallback_allowed
from app.core.config import Settings


def _settings(app_env: str) -> Settings:
    return Settings(app_env=app_env)


@pytest.mark.parametrize("env", sorted(DEV_ENV_NAMES))
def test_dev_fallback_allowed_true_for_dev_envs(env: str) -> None:
    assert dev_fallback_allowed(_settings(env)) is True


@pytest.mark.parametrize("env", ["production", "staging", "prod", "", "PROD", "anything-else"])
def test_dev_fallback_allowed_false_for_non_dev_envs(env: str) -> None:
    assert dev_fallback_allowed(_settings(env)) is False


@pytest.mark.parametrize("env", ["Development", " development ", "DEV", "Test", "LOCAL"])
def test_dev_fallback_allowed_normalizes_case_and_whitespace_for_dev_envs(env: str) -> None:
    # A miscased/padded dev value still resolves to dev (fallback allowed).
    assert dev_fallback_allowed(_settings(env)) is True


@pytest.mark.parametrize("env", ["Production", " production ", "STAGING"])
def test_dev_fallback_allowed_still_closed_for_miscased_non_dev_envs(env: str) -> None:
    # Normalization must never let a production value slip into the dev branch.
    assert dev_fallback_allowed(_settings(env)) is False


def test_dev_env_names_is_a_constant_set_of_expected_values() -> None:
    # Guard against accidental scope creep in what counts as "dev".
    assert "development" in DEV_ENV_NAMES
    assert "test" in DEV_ENV_NAMES
    assert "production" not in DEV_ENV_NAMES
    assert "staging" not in DEV_ENV_NAMES
