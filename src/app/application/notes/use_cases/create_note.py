import uuid

from app.application.notes.note_target_not_found_error import NoteTargetNotFoundError
from app.domain.notes.entities import Note
from app.domain.notes.ports import NoteRepository, NoteTargetResolver
from app.domain.notes.value_objects import NoteTargetKind


class CreateNote:
    """Creates a note, optionally linked to the object it is about.

    Resolving the target here — rather than trusting the client — is what makes two
    guarantees hold: a note can never point at something that does not exist, and its
    label cannot be spoofed or drift, because the client never sends display text.
    """

    def __init__(
        self, note_repository: NoteRepository, note_target_resolver: NoteTargetResolver
    ) -> None:
        self._note_repository = note_repository
        self._note_target_resolver = note_target_resolver

    async def execute(
        self,
        user_id: str,
        body: str,
        target_kind: NoteTargetKind | None = None,
        target_id: str | None = None,
    ) -> Note:
        target = None
        if target_kind is not None and target_id is not None:
            target = await self._note_target_resolver.resolve(target_kind, target_id)
            if target is None:
                raise NoteTargetNotFoundError(kind=target_kind, target_id=target_id)

        note = Note(id=str(uuid.uuid4()), user_id=user_id, body=body, target=target)
        return await self._note_repository.create(note)
