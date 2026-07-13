from pydantic import BaseModel, ConfigDict


class LinkedSignalResponse(BaseModel):
    """Human-readable view of one signal linked to a `Briefing`.

    The T0 briefing shape exposed only `linked_signal_ids` (raw UUIDs). The frontend
    renders each linked signal as a link to `/radar/{symbol}`, so it needs the resolved
    instrument `symbol`, the signal's `impact` direction, its `confidence`, and a short
    `title` (the signal's thesis headline) — resolved from the `Signal` entity at read
    time in the API layer, keeping the domain `Briefing` unaware of it.

    When a linked signal id can't be resolved (deleted/missing), the API degrades
    gracefully and still emits a `LinkedSignalResponse` carrying the id with a placeholder
    `symbol`, so the frontend can fall back instead of the whole briefing failing.
    """

    model_config = ConfigDict(from_attributes=True)

    signal_id: str
    symbol: str
    impact: str
    confidence: float
    title: str
