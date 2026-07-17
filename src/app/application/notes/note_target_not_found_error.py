from app.domain.notes.value_objects import NoteTargetKind


class NoteTargetNotFoundError(Exception):
    """Raised when a note is created against a target that does not exist.

    Caught by the API layer (`api/v1/routers/notes.py`) and translated to
    `422 Unprocessable Content` — you cannot annotate nothing. Same shape as
    `ReviewTargetNotFoundError`.
    """

    def __init__(self, kind: NoteTargetKind, target_id: str) -> None:
        self.kind = kind
        self.target_id = target_id
        super().__init__(f"{kind.value} '{target_id}' not found")
