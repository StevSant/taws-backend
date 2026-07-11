from pydantic import BaseModel, Field


class GenerateConsequenceChainRequest(BaseModel):
    """Request payload for `POST /api/v1/consequence-chains/generate`."""

    subject: str = Field(..., min_length=1, max_length=500)
