from pydantic import BaseModel, ConfigDict

from app.domain.notes.value_objects import NoteTargetKind


class NoteTargetResponse(BaseModel):
    """The object a note is about.

    `available` is an EXPLICIT field, not something the client reverse-engineers. This is
    the discriminator `LinkedSignalResponse` lacks — which is why the briefing card has to
    guess "archived" from `confidence === 0 && title === ''`, and guesses wrong on any
    genuinely zero-confidence signal. Do not repeat that here.
    """

    model_config = ConfigDict(from_attributes=True)

    kind: NoteTargetKind
    label: str
    target_id: str | None = None
    watchlist_id: str | None = None
    available: bool
