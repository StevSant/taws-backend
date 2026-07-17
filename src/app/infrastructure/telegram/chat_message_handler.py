import logging

from app.application.charts import deserialize_chart_spec
from app.application.telegram.use_cases import ResolveTelegramChatIdentity
from app.domain.agents.entities import ChartEvent, ErrorEvent, Message, MessageRole, TokenEvent
from app.domain.agents.ports import AgentRunner
from app.domain.charts.entities import ChartSpec
from app.domain.charts.ports import ChartImageRenderer
from app.domain.telegram.ports import TelegramMessenger
from app.infrastructure.telegram.chat_message import ChatMessage
from app.infrastructure.telegram.truncate_telegram_caption import truncate_telegram_caption

logger = logging.getLogger(__name__)


class ChatMessageHandler:
    """Routes a non-command Telegram message through the LangGraph agent and sends
    the response back to the chat.

    Uses `chat_id` as the `thread_id` so each Telegram user gets their own conversation
    history via the checkpointer.

    Identity (issue #2): `ResolveTelegramChatIdentity` maps the inbound `chat_id` to the
    linked `(user_id, locale)` — so per-user tools (watchlist, etc.) work over Telegram for
    a linked account, and a linked user is answered in their own `preferred_locale`. An
    unlinked chat streams anonymously (`user_id=""`) in `Settings.default_locale`, exactly
    as before.

    Charts (issue #1): the agent's `render_*` tools emit `ChartEvent`s that the web chat
    renders client-side; here they are accumulated during the stream, then each is rasterized
    to a PNG by `ChartImageRenderer` and delivered via `send_photo` after the text reply. One
    chart's render/send failure is logged and skipped — it never crashes the reply that was
    already sent.
    """

    def __init__(
        self,
        agent_runner: AgentRunner,
        messenger: TelegramMessenger,
        default_locale: str,
        resolve_identity: ResolveTelegramChatIdentity,
        chart_image_renderer: ChartImageRenderer,
    ) -> None:
        self._agent_runner = agent_runner
        self._messenger = messenger
        self._default_locale = default_locale
        self._resolve_identity = resolve_identity
        self._chart_image_renderer = chart_image_renderer

    async def handle(self, command: ChatMessage) -> None:
        tokens: list[str] = []
        charts: list[dict] = []
        user_id, locale = await self._resolve_identity.execute(command.chat_id)
        user_message = Message(role=MessageRole.USER, content=command.text)
        async for event in self._agent_runner.stream(
            thread_id=command.chat_id,
            message=user_message,
            user_id=user_id,
            locale=locale,
        ):
            if isinstance(event, TokenEvent):
                tokens.append(event.token)
            elif isinstance(event, ChartEvent):
                charts.append(event.chart)
            elif isinstance(event, ErrorEvent):
                await self._messenger.send_text(
                    command.chat_id,
                    "Lo siento, ocurrió un error al procesar tu mensaje.",
                )
                return
        response = "".join(tokens)
        if response.strip():
            await self._messenger.send_text(command.chat_id, response)
        for chart in charts:
            await self._send_chart(command.chat_id, chart)

    async def _send_chart(self, chat_id: str, chart: dict) -> None:
        """Render one chart to a PNG and deliver it; log and skip on any failure."""
        try:
            spec = deserialize_chart_spec(chart)
            image = await self._chart_image_renderer.render(spec)
            await self._messenger.send_photo(
                chat_id, image, caption=truncate_telegram_caption(_caption(spec))
            )
        except Exception:  # noqa: BLE001 — one bad chart must never break the delivered reply
            logger.warning("Failed to render/send a Telegram chart image", exc_info=True)


def _caption(spec: ChartSpec) -> str:
    if spec.meta.source:
        return f"{spec.meta.title} · Source: {spec.meta.source}"
    return spec.meta.title
