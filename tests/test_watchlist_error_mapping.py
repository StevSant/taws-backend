"""Watchlist API returns meaningful HTTP errors instead of a generic 500 (issue #22).

Two layers are covered:

- **Infrastructure translation** — `build_watchlist_persistence_error` maps raw PostgREST
  error codes (`23505` unique_violation, `22P02` invalid_text_representation) to watchlist
  domain errors, and returns `None` for anything else so unrelated failures still surface
  as a logged 500.
- **API mapping** — the app-level exception handlers turn those domain errors into
  `409 Conflict` (re-adding a tracked symbol) and `422` (malformed id), so the router never
  maps a Postgres code itself.
"""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from supabase import PostgrestAPIError

from app.api.middleware import (
    duplicate_watchlist_item_handler,
    invalid_watchlist_identifier_handler,
)
from app.api.v1.dependencies import get_watchlist_repository, require_current_user
from app.api.v1.routers import watchlists_router
from app.api.v1.schemas import CurrentUser
from app.domain.auth.entities import UserRole
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.errors import (
    DuplicateWatchlistItemError,
    InvalidWatchlistIdentifierError,
)
from app.infrastructure.persistence.build_watchlist_persistence_error import (
    build_watchlist_persistence_error,
)

_USER_ID = "user-1"
_WATCHLIST_ID = "watchlist-1"


# ---- Infrastructure: PostgREST code -> domain error translation -----------------------


def _postgrest_error(code: str) -> PostgrestAPIError:
    return PostgrestAPIError({"message": f"boom {code}", "code": code, "details": "", "hint": None})


def test_unique_violation_becomes_duplicate_item_error() -> None:
    translated = build_watchlist_persistence_error(_postgrest_error("23505"), symbol="AAPL")

    assert isinstance(translated, DuplicateWatchlistItemError)
    assert "AAPL" in str(translated)


def test_invalid_text_representation_becomes_invalid_identifier_error() -> None:
    translated = build_watchlist_persistence_error(_postgrest_error("22P02"))

    assert isinstance(translated, InvalidWatchlistIdentifierError)


def test_unrelated_postgrest_code_is_not_translated() -> None:
    # 42501 (RLS rejection) has no meaningful HTTP mapping — it must fall through to the
    # catch-all 500 (+ log), so the translator returns None and the caller re-raises.
    assert build_watchlist_persistence_error(_postgrest_error("42501")) is None


# ---- API: domain error -> HTTP status mapping -----------------------------------------


class _FakeWatchlistRepository:
    """Fake port raising the domain errors the real Supabase adapter would raise."""

    async def get(self, watchlist_id: str) -> Watchlist | None:
        if watchlist_id == "not-a-uuid":
            raise InvalidWatchlistIdentifierError()
        if watchlist_id == _WATCHLIST_ID:
            return Watchlist(id=_WATCHLIST_ID, user_id=_USER_ID, name="wl")
        return None

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        raise DuplicateWatchlistItemError(symbol)

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:  # pragma: no cover
        return None


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(watchlists_router, prefix="/api/v1")
    app.add_exception_handler(DuplicateWatchlistItemError, duplicate_watchlist_item_handler)
    app.add_exception_handler(InvalidWatchlistIdentifierError, invalid_watchlist_identifier_handler)
    app.dependency_overrides[get_watchlist_repository] = _FakeWatchlistRepository
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id=_USER_ID, email="u@example.io", role=UserRole.MEMBER
    )
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


def test_re_adding_a_tracked_symbol_returns_409(client: TestClient) -> None:
    resp = client.post(f"/api/v1/watchlists/{_WATCHLIST_ID}/items", json={"symbol": "AAPL"})

    assert resp.status_code == 409
    assert "AAPL" in resp.json()["detail"]


def test_malformed_watchlist_id_returns_422(client: TestClient) -> None:
    resp = client.get("/api/v1/watchlists/not-a-uuid")

    assert resp.status_code == 422


def test_valid_request_still_succeeds(client: TestClient) -> None:
    # A real uuid the fake doesn't know -> 404, proving the error handlers don't hijack
    # the normal not-found path.
    resp = client.get(f"/api/v1/watchlists/{uuid.uuid4()}")

    assert resp.status_code == 404
