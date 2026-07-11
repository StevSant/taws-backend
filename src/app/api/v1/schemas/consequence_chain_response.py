from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.consequence_edge_response import ConsequenceEdgeResponse
from app.api.v1.schemas.consequence_node_response import ConsequenceNodeResponse


class ConsequenceChainResponse(BaseModel):
    """Response payload for a single Consequence Chain Analyst-generated chain."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    subject: str
    nodes: list[ConsequenceNodeResponse]
    edges: list[ConsequenceEdgeResponse]
    disclaimer: str
    created_at: datetime
