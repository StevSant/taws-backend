from pydantic import BaseModel, Field


class InterpretMacroEventRequest(BaseModel):
    """Request payload for `POST /api/v1/macro/interpret`.

    `event_description` is optional — omit it to interpret the current macro state
    generally, per `InterpretMacroEvent.execute`'s default (see that use case's
    docstring for the "or just fetches current MacroDataProvider state proactively"
    framing from the issue).
    """

    event_description: str | None = Field(default=None, min_length=1, max_length=500)
