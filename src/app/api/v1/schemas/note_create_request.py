from pydantic import BaseModel, Field, model_validator

from app.domain.notes.value_objects import NoteTargetKind


class NoteCreateRequest(BaseModel):
    """Payload for creating a note, optionally about a briefing/scenario/instrument.

    There is deliberately no `target_label`: labels are resolved server-side, so the
    client cannot spoof one or let it drift. An unknown extra field is ignored by
    Pydantic's default, which is what we want — it must never reach the label.
    """

    body: str = Field(..., min_length=1, max_length=2000)
    target_kind: NoteTargetKind | None = None
    target_id: str | None = None

    @model_validator(mode="after")
    def _kind_and_id_come_as_a_pair(self) -> "NoteCreateRequest":
        if (self.target_kind is None) != (self.target_id is None):
            raise ValueError("target_kind and target_id must be provided together")
        return self
