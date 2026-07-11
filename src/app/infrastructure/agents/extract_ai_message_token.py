from langchain_core.messages import AIMessageChunk, BaseMessage


def extract_ai_message_token(message_chunk: BaseMessage) -> str | None:
    """Return the text content of an AI message chunk, or `None` to skip it.

    Used by `LangGraphAgentRunner.stream` to filter a `stream_mode="messages"`
    stream down to plain assistant tokens: non-`AIMessageChunk` entries (tool-call
    deltas, echoed human/system messages) and empty content are both skipped.
    """
    if not isinstance(message_chunk, AIMessageChunk):
        return None
    content = message_chunk.content
    return content if isinstance(content, str) and content else None
