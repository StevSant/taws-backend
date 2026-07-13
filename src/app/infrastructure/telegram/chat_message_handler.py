import logging

from app.domain.agents.entities import ErrorEvent, Message, MessageRole, TokenEvent
from app.domain.agents.ports import AgentRunner
from app.domain.telegram.ports import TelegramMessenger
from app.infrastructure.telegram.chat_message import ChatMessage

logger = logging.getLogger(__name__)


class ChatMessageHandler:
    """Routes a non-command Telegram message through the LangGraph agent and sends
    the response back to the chat.

    Uses `chat_id` as the `thread_id` so each Telegram user gets their own
    conversation history via the checkpointer.

    `default_locale` (injected from `Settings`, via the DI container — same shape as
    `SimulateCommandHandler`) is the language the agent answers Telegram in. Unlike the web
    chat, this path has no `CurrentUser` to look a `preferred_locale` up from: it streams
    with `user_id=""`, and the Telegram link table maps a chat id to a user, not the other
    way round. Per-user Telegram locale is a follow-up; the configured default is correct
    for the whole audience today.
    """

    def __init__(
        self, agent_runner: AgentRunner, messenger: TelegramMessenger, default_locale: str
    ) -> None:
        self._agent_runner = agent_runner
        self._messenger = messenger
        self._default_locale = default_locale

    async def handle(self, command: ChatMessage) -> None:
        tokens: list[str] = []
        user_message = Message(role=MessageRole.USER, content=command.text)
        async for event in self._agent_runner.stream(
            thread_id=command.chat_id,
            message=user_message,
            user_id="",
            locale=self._default_locale,
        ):
            if isinstance(event, TokenEvent):
                tokens.append(event.token)
            elif isinstance(event, ErrorEvent):
                await self._messenger.send_text(
                    command.chat_id,
                    "Lo siento, ocurrió un error al procesar tu mensaje.",
                )
                return
        response = "".join(tokens)
        if response.strip():
            await self._messenger.send_text(command.chat_id, response)
