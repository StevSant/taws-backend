from contextlib import suppress

from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.telegram.entities import InlineButton
from app.infrastructure.telegram.build_event_callback_data import (
    CallbackDataTooLongError,
    build_event_callback_data,
)
from app.infrastructure.telegram.event_callback_action import EventCallbackAction
from app.infrastructure.telegram.is_telegram_compatible_url import is_telegram_compatible_url

# Telegram renders long button labels by truncating them mid-word; a suggested question is a
# full sentence, so it has to be shortened deliberately rather than left to the client.
_MAX_QUESTION_LABEL_CHARS = 48
# One question per row (they're long). More than this and the alert becomes a wall of buttons.
_MAX_QUESTION_BUTTONS = 3


def build_event_alert_buttons(
    event: EnrichedEvent, frontend_base_url: str, *, news_id: str | None = None
) -> list[list[InlineButton]]:
    """Build the inline keyboard under a Sentinel alert.

    When the caller knows the persisted news id, the web-app button opens that article's detail;
    scheduled alerts without that id fall back to the news list. Local frontend URLs cannot be
    opened by Telegram, so the web-app button is omitted in local development. The callback
    buttons remain available because Telegram sends those updates to the configured bot webhook.
    """
    rows: list[list[InlineButton]] = []
    news_path = f"/radar/news/{news_id}" if news_id else "/radar/news"
    news_url = f"{frontend_base_url.rstrip('/')}{news_path}"
    if is_telegram_compatible_url(news_url):
        rows.append([InlineButton(text="📊 Ver en TAWS", url=news_url)])

    with suppress(CallbackDataTooLongError):
        rows.append(
            [
                InlineButton(
                    text="📈 Analizar impacto",
                    callback_data=build_event_callback_data(
                        EventCallbackAction.ANALYZE_IMPACT, event.id
                    ),
                )
            ]
        )

    for index, question in enumerate(event.suggested_questions[:_MAX_QUESTION_BUTTONS]):
        try:
            data = build_event_callback_data(
                EventCallbackAction.ASK_QUESTION, event.id, question_index=index
            )
        except CallbackDataTooLongError:
            continue
        rows.append([InlineButton(text=f"💬 {_shorten(question)}", callback_data=data)])

    return rows


def _shorten(question: str) -> str:
    if len(question) <= _MAX_QUESTION_LABEL_CHARS:
        return question
    return question[: _MAX_QUESTION_LABEL_CHARS - 1].rstrip() + "…"
