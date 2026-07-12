"""Endpoint RBAC tests for the review write/read paths (product matrix).

Matrix:
    - POST /api/v1/signals/{id}/reviews    -> COMPLIANCE only (403 for other roles)
    - POST /api/v1/briefings/{id}/reviews  -> COMPLIANCE only (403 for other roles)
    - GET  review-history endpoints        -> any authenticated user
    - anonymous                            -> 401 (never downgraded to 403)

Compliance write invariants also checked here:
    - a compliance user can review a briefing they do NOT own (write path drops the
      ownership gate so compliance can review ANY user's briefing)
    - justification is mandatory (422 on blank)
    - the audit trail is append-only and persists the ACTING user's id
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.dependencies import (
    get_briefing_repository,
    get_signal_repository,
    get_watchlist_repository,
    require_current_user,
)
from app.api.v1.routers import reviews_router
from app.api.v1.schemas import CurrentUser
from app.domain.auth.entities import UserRole
from app.domain.briefing.entities import Briefing
from app.domain.review.entities import ReviewState
from app.domain.signals.entities.signal import Signal
from app.domain.watchlist.entities import Watchlist

_SIGNAL_ID = "signal-1"
_BRIEFING_ID = "briefing-1"
_COMPLIANCE_USER_ID = "compliance-user"
_OWNER_USER_ID = "owner-user"  # owns the briefing; is NOT the reviewer


class _FakeSignalRepository:
    def __init__(self) -> None:
        self._signal = Signal(
            id=_SIGNAL_ID,
            instrument_symbol="AAPL",
            impact_class=_first_impact_class(),
            confidence=0.9,
            evidence=[],
            disclaimer="not advice",
        )
        self.saved: list[ReviewState] = []

    async def get(self, signal_id: str) -> Signal | None:
        return self._signal if signal_id == _SIGNAL_ID else None

    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        return [s for s in self.saved if s.entity_id == signal_id]

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        self.saved.append(review_state)
        return review_state


class _FakeBriefingRepository:
    def __init__(self) -> None:
        self._briefing = Briefing(
            id=_BRIEFING_ID,
            watchlist_id="watchlist-1",
            summary="summary",
            disclaimer="not advice",
        )
        self.saved: list[ReviewState] = []

    async def get(self, briefing_id: str) -> Briefing | None:
        return self._briefing if briefing_id == _BRIEFING_ID else None

    async def list_review_states(self, briefing_id: str) -> list[ReviewState]:
        return [s for s in self.saved if s.entity_id == briefing_id]

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        self.saved.append(review_state)
        return review_state


class _FakeWatchlistRepository:
    """The briefing's watchlist is owned by `_OWNER_USER_ID`, not the reviewer."""

    async def get(self, watchlist_id: str) -> Watchlist | None:
        if watchlist_id == "watchlist-1":
            return Watchlist(id="watchlist-1", user_id=_OWNER_USER_ID, name="wl")
        return None


def _first_impact_class() -> Any:
    from app.domain.signals.entities.impact_class import ImpactClass

    return next(iter(ImpactClass))


@pytest.fixture
def signal_repo() -> _FakeSignalRepository:
    return _FakeSignalRepository()


@pytest.fixture
def briefing_repo() -> _FakeBriefingRepository:
    return _FakeBriefingRepository()


def _build_app(
    signal_repo: _FakeSignalRepository,
    briefing_repo: _FakeBriefingRepository,
    *,
    user: CurrentUser | None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(reviews_router, prefix="/api/v1")
    app.dependency_overrides[get_signal_repository] = lambda: signal_repo
    app.dependency_overrides[get_briefing_repository] = lambda: briefing_repo
    app.dependency_overrides[get_watchlist_repository] = _FakeWatchlistRepository

    if user is None:
        # Anonymous: the real auth dependency raises 401 (import inside to reuse the
        # actual guard rather than faking it).
        from fastapi import HTTPException, status

        def _anonymous() -> CurrentUser:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

        app.dependency_overrides[require_current_user] = _anonymous
    else:
        app.dependency_overrides[require_current_user] = lambda: user
    return app


def _user(role: UserRole, *, user_id: str = _COMPLIANCE_USER_ID) -> CurrentUser:
    return CurrentUser(id=user_id, email="reviewer@example.io", role=role)


# ---- Compliance write happy paths ------------------------------------------------------


def test_compliance_can_submit_signal_review(
    signal_repo: _FakeSignalRepository, briefing_repo: _FakeBriefingRepository
) -> None:
    app = _build_app(signal_repo, briefing_repo, user=_user(UserRole.COMPLIANCE))
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/signals/{_SIGNAL_ID}/reviews",
        json={"decision": "reviewed", "justification": "looks fine"},
    )
    assert resp.status_code == 201
    # Acting user id is persisted, taken from the authenticated user (not the body).
    assert signal_repo.saved[0].user_id == _COMPLIANCE_USER_ID


def test_compliance_can_review_a_briefing_it_does_not_own(
    signal_repo: _FakeSignalRepository, briefing_repo: _FakeBriefingRepository
) -> None:
    # The briefing's watchlist belongs to _OWNER_USER_ID; the reviewer is a DIFFERENT
    # compliance user. The write path must NOT 404 on cross-user briefings.
    app = _build_app(signal_repo, briefing_repo, user=_user(UserRole.COMPLIANCE))
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/briefings/{_BRIEFING_ID}/reviews",
        json={"decision": "reviewed", "justification": "reviewed for compliance"},
    )
    assert resp.status_code == 201
    assert briefing_repo.saved[0].user_id == _COMPLIANCE_USER_ID


# ---- Non-compliance roles are blocked (403) -------------------------------------------


@pytest.mark.parametrize("role", [UserRole.ANALYST, UserRole.PORTFOLIO, UserRole.MEMBER])
def test_non_compliance_cannot_submit_signal_review(
    role: UserRole,
    signal_repo: _FakeSignalRepository,
    briefing_repo: _FakeBriefingRepository,
) -> None:
    app = _build_app(signal_repo, briefing_repo, user=_user(role))
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/signals/{_SIGNAL_ID}/reviews",
        json={"decision": "reviewed", "justification": "nope"},
    )
    assert resp.status_code == 403
    assert signal_repo.saved == []


@pytest.mark.parametrize("role", [UserRole.ANALYST, UserRole.PORTFOLIO, UserRole.MEMBER])
def test_non_compliance_cannot_submit_briefing_review(
    role: UserRole,
    signal_repo: _FakeSignalRepository,
    briefing_repo: _FakeBriefingRepository,
) -> None:
    app = _build_app(signal_repo, briefing_repo, user=_user(role))
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/briefings/{_BRIEFING_ID}/reviews",
        json={"decision": "reviewed", "justification": "nope"},
    )
    assert resp.status_code == 403
    assert briefing_repo.saved == []


# ---- Anonymous -> 401, never 403 -------------------------------------------------------


def test_anonymous_signal_review_is_401_not_403(
    signal_repo: _FakeSignalRepository, briefing_repo: _FakeBriefingRepository
) -> None:
    app = _build_app(signal_repo, briefing_repo, user=None)
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/signals/{_SIGNAL_ID}/reviews",
        json={"decision": "reviewed", "justification": "x"},
    )
    assert resp.status_code == 401


def test_anonymous_briefing_review_is_401_not_403(
    signal_repo: _FakeSignalRepository, briefing_repo: _FakeBriefingRepository
) -> None:
    app = _build_app(signal_repo, briefing_repo, user=None)
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/briefings/{_BRIEFING_ID}/reviews",
        json={"decision": "reviewed", "justification": "x"},
    )
    assert resp.status_code == 401


# ---- GET history stays open to any authenticated user ---------------------------------


def test_non_compliance_can_get_signal_review_history(
    signal_repo: _FakeSignalRepository, briefing_repo: _FakeBriefingRepository
) -> None:
    app = _build_app(signal_repo, briefing_repo, user=_user(UserRole.ANALYST))
    client = TestClient(app)
    resp = client.get(f"/api/v1/signals/{_SIGNAL_ID}/reviews")
    assert resp.status_code == 200
    assert resp.json() == []


def test_owner_can_get_briefing_review_history(
    signal_repo: _FakeSignalRepository, briefing_repo: _FakeBriefingRepository
) -> None:
    # GET briefing history keeps the ownership gate; the owner (analyst role) can read it.
    app = _build_app(
        signal_repo, briefing_repo, user=_user(UserRole.ANALYST, user_id=_OWNER_USER_ID)
    )
    client = TestClient(app)
    resp = client.get(f"/api/v1/briefings/{_BRIEFING_ID}/reviews")
    assert resp.status_code == 200


# ---- Justification mandatory + append-only audit trail --------------------------------


def test_blank_justification_is_rejected(
    signal_repo: _FakeSignalRepository, briefing_repo: _FakeBriefingRepository
) -> None:
    app = _build_app(signal_repo, briefing_repo, user=_user(UserRole.COMPLIANCE))
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/signals/{_SIGNAL_ID}/reviews",
        json={"decision": "reviewed", "justification": "   "},
    )
    assert resp.status_code == 422
    assert signal_repo.saved == []


def test_review_trail_is_append_only(
    signal_repo: _FakeSignalRepository, briefing_repo: _FakeBriefingRepository
) -> None:
    app = _build_app(signal_repo, briefing_repo, user=_user(UserRole.COMPLIANCE))
    client = TestClient(app)
    # ESCALATED is non-terminal, so a second decision (-> REVIEWED) is a legal transition
    # and appends a new row rather than mutating the first.
    first = client.post(
        f"/api/v1/signals/{_SIGNAL_ID}/reviews",
        json={"decision": "escalated", "justification": "needs another look"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/signals/{_SIGNAL_ID}/reviews",
        json={"decision": "reviewed", "justification": "resolved"},
    )
    assert second.status_code == 201
    # Two distinct rows recorded — the first is never mutated.
    assert len(signal_repo.saved) == 2
    assert signal_repo.saved[0].decision == "escalated"
    assert signal_repo.saved[1].decision == "reviewed"
