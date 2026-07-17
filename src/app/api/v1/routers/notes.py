from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.dependencies import get_create_note, get_note_repository, require_current_user
from app.api.v1.schemas import CurrentUser, NoteBodyRequest, NoteCreateRequest, NoteResponse
from app.application.notes import NoteTargetNotFoundError
from app.application.notes.use_cases import CreateNote
from app.domain.notes.entities import Note
from app.domain.notes.ports import NoteRepository

router = APIRouter(prefix="/notes", tags=["notes"])


async def _get_owned_note(note_id: str, user: CurrentUser, repository: NoteRepository) -> Note:
    """Return the note if it exists and belongs to `user`, else raise 404.

    404 (not 403) even when the note exists but belongs to someone else, so this endpoint
    never confirms another user's note id exists — same ownership-check shape as
    `watchlists.py`'s `_get_owned_watchlist`.
    """
    note = await repository.get(note_id)
    if note is None or note.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@router.get("")
async def list_notes(
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[NoteRepository, Depends(get_note_repository)],
) -> list[NoteResponse]:
    """List every note owned by the authenticated user, most-recently-updated first."""
    notes = await repository.list_for_user(user.id)
    return [NoteResponse.model_validate(note) for note in notes]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreateRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    use_case: Annotated[CreateNote, Depends(get_create_note)],
) -> NoteResponse:
    """Create a note owned by the authenticated user, optionally about a target.

    A target that does not exist is a 422, not a silently-unlinked note: the user asked to
    annotate a specific thing, and quietly dropping the link would lie about what happened.
    """
    try:
        created = await use_case.execute(
            user_id=user.id,
            body=payload.body,
            target_kind=payload.target_kind,
            target_id=payload.target_id,
        )
    except NoteTargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return NoteResponse.model_validate(created)


@router.patch("/{note_id}")
async def update_note(
    note_id: str,
    payload: NoteBodyRequest,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[NoteRepository, Depends(get_note_repository)],
) -> NoteResponse:
    """Update the body of a note owned by the authenticated user."""
    await _get_owned_note(note_id, user, repository)
    updated = await repository.update(note_id, payload.body)
    return NoteResponse.model_validate(updated)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    user: Annotated[CurrentUser, Depends(require_current_user)],
    repository: Annotated[NoteRepository, Depends(get_note_repository)],
) -> None:
    """Delete a note owned by the authenticated user."""
    await _get_owned_note(note_id, user, repository)
    await repository.delete(note_id)
