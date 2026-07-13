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
    # Optional so the endpoint keeps working for callers that only want a title computed.
    # When present, the generated title is also SAVED onto that conversation, so the sidebar
    # shows the same title after a reload or on another device instead of re-deriving one
    # from the first message locally.
    thread_id: str | None = Field(
        default=None,
        description="Conversation to persist the generated title onto; omit to only compute it.",
    )
