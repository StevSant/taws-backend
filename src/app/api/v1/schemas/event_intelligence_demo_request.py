from pydantic import BaseModel, Field


class EventIntelligenceDemoRequest(BaseModel):
    """Request payload for `POST /api/v1/event-intelligence/demo`.

    Allows manual injection of a news event into the Event Intelligence pipeline.
    """

    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=2000)
    content: str = Field(min_length=1, max_length=10000)
    source: str = Field(default="manual", max_length=100)
