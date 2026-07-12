from pydantic import BaseModel, Field

from app.api.v1.schemas.chat_title_message import ChatTitleMessage


class GenerateTitleRequest(BaseModel):
    """Request payload for `POST /api/v1/chat/title`.

    Carries the conversation so far (at least the first user/assistant exchange); the
    endpoint returns a concise topic title for it.
    """

    messages: list[ChatTitleMessage] = Field(
        ..., description="The conversation messages, in order."
    )
