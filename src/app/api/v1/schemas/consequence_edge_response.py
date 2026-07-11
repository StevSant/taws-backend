from pydantic import BaseModel, ConfigDict


class ConsequenceEdgeResponse(BaseModel):
    """Response payload for one edge in a `ConsequenceChain`."""

    model_config = ConfigDict(from_attributes=True)

    source_node_id: str
    target_node_id: str
    mechanism: str
    confidence: float
