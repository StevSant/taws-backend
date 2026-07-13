from typing import Any

from app.infrastructure.realtime.ws.openai_events import (
    OPENAI_ERROR,
    OPENAI_OUTPUT_AUDIO_DELTA,
    OPENAI_OUTPUT_AUDIO_DONE,
    OPENAI_OUTPUT_AUDIO_TRANSCRIPT_DELTA,
    OPENAI_RESPONSE_DONE,
    OPENAI_SPEECH_STARTED,
)


def map_openai_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Map one OpenAI Realtime server event to the browser message the client expects.

    Returns the small JSON message to forward on the browser socket, or `None` for events
    the browser doesn't need (dropped). Pure: no I/O, so the whole translation layer is
    unit-tested with plain dicts. The event-type strings live in `openai_events` so a live
    rename is a one-line fix there.

    Mappings:
    - `response.output_audio.delta` -> `{type: "audio", data: <b64 pcm16>}`
    - `response.output_audio_transcript.delta` -> `{type: "transcript-delta", delta}`
    - `input_audio_buffer.speech_started` -> `{type: "speaking", speaking: true}` (barge-in)
    - `response.output_audio.done` / `response.done` -> `{type: "speaking", speaking: false}`
    - `error` -> `{type: "error", message}`
    - anything else (incl. a typeless event) -> `None`
    """
    event_type = event.get("type")
    if event_type is None:
        return None

    if event_type == OPENAI_OUTPUT_AUDIO_DELTA:
        return {"type": "audio", "data": event.get("delta", "")}
    if event_type == OPENAI_OUTPUT_AUDIO_TRANSCRIPT_DELTA:
        return {"type": "transcript-delta", "delta": event.get("delta", "")}
    if event_type == OPENAI_SPEECH_STARTED:
        return {"type": "speaking", "speaking": True}
    if event_type in (OPENAI_OUTPUT_AUDIO_DONE, OPENAI_RESPONSE_DONE):
        return {"type": "speaking", "speaking": False}
    if event_type == OPENAI_ERROR:
        error = event.get("error")
        message = error.get("message") if isinstance(error, dict) else str(error)
        return {"type": "error", "message": message}
    return None
