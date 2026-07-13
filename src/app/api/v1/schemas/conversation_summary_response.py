from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationSummaryResponse(BaseModel):
    """One conversation in the sidebar list (`GET /chat/conversations`).

    Carries no messages on purpose — the list only renders a title and a timestamp, so
    shipping every turn of every thread would be a large payload nobody reads. The turns
    arrive with `GET /chat/conversations/{id}`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
