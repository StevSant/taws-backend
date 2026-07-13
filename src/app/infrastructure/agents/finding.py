from pydantic import BaseModel, Field

from app.infrastructure.agents.source import Source


class Finding(BaseModel):
    claim: str = Field(min_length=1)
    source: Source
