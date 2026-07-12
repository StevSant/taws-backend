"""Tests for `_verify_telegram_secret` — the Telegram webhook auth guard.

Fail-closed contract (mirrors `require_current_user`): when
`TELEGRAM_WEBHOOK_SECRET` is unset, an anonymous POST is only accepted in a
development/test env. In production the webhook must reject with 403 instead of
processing any anonymous update.

    secret set   + right header -> allowed
    secret set   + wrong header -> 401
    secret unset + app_env=development -> allowed (permissive dev)
    secret unset + app_env=production  -> 403  (fail closed)
"""

import pytest
from fastapi import HTTPException, status

from app.api.v1.routers.telegram import _verify_telegram_secret
from app.core.config import Settings

_SECRET = "webhook-secret"


class _FakeRequest:
    def __init__(self, header_value: str | None = None) -> None:
        self.headers = {}
        if header_value is not None:
            self.headers["X-Telegram-Bot-Api-Secret-Token"] = header_value


def _settings(*, app_env: str = "development", secret: str | None = None) -> Settings:
    return Settings(app_env=app_env, telegram_webhook_secret=secret)


def test_secret_set_with_matching_header_is_allowed() -> None:
    _verify_telegram_secret(_FakeRequest(_SECRET), _settings(secret=_SECRET))


def test_secret_set_with_wrong_header_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        _verify_telegram_secret(_FakeRequest("nope"), _settings(secret=_SECRET))
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_secret_unset_in_development_is_allowed() -> None:
    _verify_telegram_secret(_FakeRequest(None), _settings(app_env="development", secret=None))


def test_secret_unset_in_production_raises_403() -> None:
    with pytest.raises(HTTPException) as exc:
        _verify_telegram_secret(_FakeRequest(None), _settings(app_env="production", secret=None))
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
