"""Endpoint tests for note target linkage.

No conftest.py and no database, matching this repo's convention: fakes are local to the
test file and wired through `app.dependency_overrides` using the production dependency
functions as keys.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_create_note, get_note_repository, require_current_user
from app.api.v1.routers import notes_router
from app.api.v1.schemas import CurrentUser
from app.application.notes.use_cases import CreateNote
from app.domain.auth.entities import UserRole
from app.domain.notes.value_objects import NoteTarget, NoteTargetKind
from app.infrastructure.persistence import InMemoryNoteRepository

_USER_ID = "user-1"

_LIVE_BRIEFING = NoteTarget(
    kind=NoteTargetKind.BRIEFING,
    label="Crypto weakness after CPI",
    target_id="briefing-1",
    watchlist_id="watchlist-9",
)


class _FakeResolver:
    """Resolves exactly one known briefing; everything else is gone."""

    async def resolve(self, kind: NoteTargetKind, target_id: str) -> NoteTarget | None:
        if kind is NoteTargetKind.BRIEFING and target_id == "briefing-1":
            return _LIVE_BRIEFING
        return None


@pytest.fixture
def repository() -> InMemoryNoteRepository:
    return InMemoryNoteRepository()


def _client(repository: InMemoryNoteRepository) -> TestClient:
    app = FastAPI()
    app.include_router(notes_router, prefix="/api/v1")
    use_case = CreateNote(repository, _FakeResolver())
    app.dependency_overrides[get_note_repository] = lambda: repository
    app.dependency_overrides[get_create_note] = lambda: use_case
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id=_USER_ID, email="user@example.io", role=UserRole.ANALYST
    )
    return TestClient(app)


def test_creating_an_unlinked_note_returns_a_null_target(
    repository: InMemoryNoteRepository,
) -> None:
    response = _client(repository).post("/api/v1/notes", json={"body": "Plain thought"})

    assert response.status_code == 201
    assert response.json()["target"] is None


def test_creating_a_linked_note_returns_the_server_resolved_target(
    repository: InMemoryNoteRepository,
) -> None:
    response = _client(repository).post(
        "/api/v1/notes",
        json={"body": "Watch it", "target_kind": "briefing", "target_id": "briefing-1"},
    )

    assert response.status_code == 201
    assert response.json()["target"] == {
        "kind": "briefing",
        "label": "Crypto weakness after CPI",
        "target_id": "briefing-1",
        "watchlist_id": "watchlist-9",
        "available": True,
    }


def test_creating_against_a_missing_target_is_422(repository: InMemoryNoteRepository) -> None:
    response = _client(repository).post(
        "/api/v1/notes",
        json={"body": "Doomed", "target_kind": "briefing", "target_id": "gone"},
    )

    assert response.status_code == 422


def test_a_client_supplied_label_is_ignored_not_honoured(
    repository: InMemoryNoteRepository,
) -> None:
    """The client never sends display text; a stray field must not become the label."""
    response = _client(repository).post(
        "/api/v1/notes",
        json={
            "body": "Spoof attempt",
            "target_kind": "briefing",
            "target_id": "briefing-1",
            "target_label": "TOTALLY DIFFERENT",
        },
    )

    assert response.status_code == 201
    assert response.json()["target"]["label"] == "Crypto weakness after CPI"


def test_an_unknown_kind_is_rejected(repository: InMemoryNoteRepository) -> None:
    response = _client(repository).post(
        "/api/v1/notes",
        json={"body": "Nope", "target_kind": "signal", "target_id": "signal-1"},
    )

    assert response.status_code == 422


def test_listing_returns_linked_and_unlinked_notes_together(
    repository: InMemoryNoteRepository,
) -> None:
    client = _client(repository)
    client.post("/api/v1/notes", json={"body": "Plain"})
    client.post(
        "/api/v1/notes",
        json={"body": "Linked", "target_kind": "briefing", "target_id": "briefing-1"},
    )

    response = client.get("/api/v1/notes")

    assert response.status_code == 200
    targets = [note["target"] for note in response.json()]
    assert len(targets) == 2
    assert None in targets


def test_patch_cannot_retarget_a_note(repository: InMemoryNoteRepository) -> None:
    client = _client(repository)
    created = client.post(
        "/api/v1/notes",
        json={"body": "Linked", "target_kind": "briefing", "target_id": "briefing-1"},
    ).json()

    response = client.patch(
        f"/api/v1/notes/{created['id']}",
        json={"body": "Edited", "target_kind": "scenario", "target_id": "scenario-1"},
    )

    assert response.status_code == 200
    assert response.json()["body"] == "Edited"
    assert response.json()["target"]["kind"] == "briefing"
