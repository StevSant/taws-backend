from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider

_MAX_TITLE_WORDS = 6
_MAX_TITLE_CHARS = 60
_TITLE_TRIM_CHARS = " .,:;—-\"'"

_TITLE_INSTRUCTION = """Generate a short topic title for the conversation below, in the \
same language the user is writing in. Rules: 3 to 6 words; describe the topic, not a \
greeting; no surrounding quotes and no trailing punctuation. Reply with the title only, \
nothing else."""


class GenerateConversationTitle:
    """Generate a concise 3-6 word topic title for a conversation via the LLM.

    Reuses the Midas voice: `voice_preamble` is injected by the DI container (which
    passes the top-level Midas persona) so `application/` stays pure and never imports
    the infrastructure persona. Degrades gracefully — when the LLM is unavailable (no
    API key placeholder, empty output, or any error) it falls back to a short slice of
    the first user message, mirroring the frontend's transient fallback.
    """

    def __init__(self, llm_provider: LLMProvider, voice_preamble: str) -> None:
        self._llm_provider = llm_provider
        self._voice_preamble = voice_preamble

    async def execute(self, messages: list[Message]) -> str:
        fallback = self._fallback_title(messages)
        excerpt = self._build_excerpt(messages)
        if not excerpt:
            return fallback

        prompt = [
            Message(
                role=MessageRole.SYSTEM,
                content=f"{self._voice_preamble}\n\n{_TITLE_INSTRUCTION}",
            ),
            Message(role=MessageRole.USER, content=excerpt),
        ]
        try:
            raw = await self._llm_provider.complete(prompt)
        except Exception:  # noqa: BLE001 — any LLM failure degrades to the fallback title
            return fallback

        return self._clean(raw) or fallback

    def _build_excerpt(self, messages: list[Message]) -> str:
        lines = [
            f"{message.role.value}: {message.content.strip()}"
            for message in messages
            if message.role in (MessageRole.USER, MessageRole.ASSISTANT) and message.content.strip()
        ]
        return "\n".join(lines)

    def _fallback_title(self, messages: list[Message]) -> str:
        for message in messages:
            if message.role == MessageRole.USER and message.content.strip():
                words = message.content.split()
                return " ".join(words[:_MAX_TITLE_WORDS])
        return ""

    def _clean(self, raw: str) -> str:
        text = " ".join(raw.split())
        # The no-key OpenAIProvider placeholder starts with a bracketed marker; treat it
        # as "no real title" so the caller falls back.
        if not text or text.startswith("["):
            return ""
        words = text.split(" ")
        if len(words) > _MAX_TITLE_WORDS:
            text = " ".join(words[:_MAX_TITLE_WORDS])
        return text[:_MAX_TITLE_CHARS].strip(_TITLE_TRIM_CHARS)
