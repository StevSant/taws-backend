"""Tests for `map_openai_event` — pure OpenAI-server-event -> browser-message mapper.

Each OpenAI Realtime event the browser cares about maps to one small JSON message on the
browser socket; everything else maps to `None` (dropped). Keeping this pure means the
whole translation layer is unit-tested with plain dicts — no socket, no OpenAI.
"""

from app.infrastructure.realtime.ws.map_openai_event import map_openai_event


def test_audio_delta_maps_to_audio_message() -> None:
    out = map_openai_event({"type": "response.output_audio.delta", "delta": "QUJD"})
    assert out == {"type": "audio", "data": "QUJD"}


def test_transcript_delta_maps_to_transcript_delta() -> None:
    out = map_openai_event({"type": "response.output_audio_transcript.delta", "delta": "Apple "})
    assert out == {"type": "transcript-delta", "delta": "Apple "}


def test_speech_started_maps_to_speaking_true() -> None:
    out = map_openai_event({"type": "input_audio_buffer.speech_started"})
    assert out == {"type": "speaking", "speaking": True}


def test_output_audio_done_maps_to_speaking_false() -> None:
    out = map_openai_event({"type": "response.output_audio.done"})
    assert out == {"type": "speaking", "speaking": False}


def test_response_done_maps_to_speaking_false() -> None:
    out = map_openai_event({"type": "response.done", "response": {"output": []}})
    assert out == {"type": "speaking", "speaking": False}


def test_error_event_maps_to_error_message() -> None:
    out = map_openai_event({"type": "error", "error": {"message": "bad audio format"}})
    assert out == {"type": "error", "message": "bad audio format"}


def test_unknown_event_maps_to_none() -> None:
    assert map_openai_event({"type": "response.created"}) is None


def test_event_without_type_maps_to_none() -> None:
    assert map_openai_event({"delta": "orphan"}) is None
