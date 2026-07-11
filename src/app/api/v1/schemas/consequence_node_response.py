from pydantic import BaseModel, ConfigDict


class ConsequenceNodeResponse(BaseModel):
    """Response payload for one node in a `ConsequenceChain`."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
