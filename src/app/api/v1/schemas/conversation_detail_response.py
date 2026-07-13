from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.v1.schemas.conversation_message_response import ConversationMessageResponse


class ConversationDetailResponse(BaseModel):
    """One conversation and all of its turns (`GET /chat/conversations/{id}`).

    This is what rehydrates the transcript when a user reopens a thread — including on a
    new device, which the previous localStorage-only frontend could not do.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageResponse]
