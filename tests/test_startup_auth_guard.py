"""Tests for the startup auth-misconfiguration guard in `main._warn_on_misconfigured_auth`.

It must log `critical` (but never raise) when a non-dev env boots without a Supabase JWT
secret, and stay quiet in development or when the secret is present.
"""

import logging

from app.core.config import Settings
from app.main import _warn_on_misconfigured_auth


def _settings(*, app_env: str, secret: str | None = None, tg_secret: str | None = None) -> Settings:
    return Settings(
        app_env=app_env,
        supabase_jwt_secret=secret,
        telegram_webhook_secret=tg_secret,
    )


def test_logs_critical_when_prod_and_jwt_secret_unset(caplog) -> None:
    with caplog.at_level(logging.CRITICAL):
        _warn_on_misconfigured_auth(_settings(app_env="production", secret=None))
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_does_not_raise_when_prod_and_jwt_secret_unset() -> None:
    # Must never crash boot — App Runner injects the secret out-of-band.
    _warn_on_misconfigured_auth(_settings(app_env="production", secret=None))


def test_no_critical_in_development(caplog) -> None:
    with caplog.at_level(logging.CRITICAL):
        _warn_on_misconfigured_auth(_settings(app_env="development", secret=None))
    assert not any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_no_critical_when_prod_secret_is_set(caplog) -> None:
    with caplog.at_level(logging.CRITICAL):
        _warn_on_misconfigured_auth(_settings(app_env="production", secret="present"))
    assert not any(r.levelno == logging.CRITICAL for r in caplog.records)
