from contextlib import suppress

from app.domain.event_intelligence.entities import EnrichedEvent
from app.domain.telegram.entities import InlineButton
from app.infrastructure.telegram.build_event_callback_data import (
    CallbackDataTooLongError,
    build_event_callback_data,
)
from app.infrastructure.telegram.event_callback_action import EventCallbackAction

# Telegram renders long button labels by truncating them mid-word; a suggested question is a
# full sentence, so it has to be shortened deliberately rather than left to the client.
_MAX_QUESTION_LABEL_CHARS = 48
# One question per row (they're long). More than this and the alert becomes a wall of buttons.
_MAX_QUESTION_BUTTONS = 3


def build_event_alert_buttons(
    event: EnrichedEvent, frontend_base_url: str
) -> list[list[InlineButton]]:
    """Build the inline keyboard under a broadcast news alert.

    Three kinds of action, one per row group:

    - **Ver en TAWS** — a plain URL button into the web app. No server round-trip.
    - **Analizar impacto** — a callback that runs the existing `AnalyzeEventImpact` (Gemini)
      pass on this event and replies in-thread.
    - **Suggested questions** — the analyzer already generates `suggested_questions` on every
      event and they were previously rendered as inert bullet text in the message body. As
      buttons they become one tap into the conversational agent, which already handles free
      text from Telegram.

    A question whose token would blow the 64-byte `callback_data` budget is skipped rather than
    allowed to fail the whole `sendMessage` — losing one button beats losing the alert.
    """
    rows: list[list[InlineButton]] = [
        [InlineButton(text="📊 Ver en TAWS", url=f"{frontend_base_url.rstrip('/')}/radar/news")]
    ]

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
