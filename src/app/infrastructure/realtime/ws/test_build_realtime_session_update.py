"""Tests for `build_realtime_session_update` — the pure `session.update` builder.

The WS proxy sends exactly one `session.update` after `session.created`, configuring the
same server-authored tools + instructions the WebRTC path uses, plus the pcm16/voice/VAD
audio settings. Pure function -> no OpenAI, no socket.
"""

from app.core.config import Settings
from app.infrastructure.realtime.build_realtime_instructions import build_realtime_instructions
from app.infrastructure.realtime.ws.build_realtime_session_update import (
    build_realtime_session_update,
)


def _settings() -> Settings:
    return Settings(openai_realtime_voice="verse")


def test_type_is_session_update() -> None:
    assert build_realtime_session_update(_settings(), "es")["type"] == "session.update"


def test_includes_server_authored_instructions() -> None:
    session = build_realtime_session_update(_settings(), "es")["session"]
    assert session["instructions"] == build_realtime_instructions("es")


def test_instructions_pin_the_requested_locale() -> None:
    """The voice agent used to be handed a bare English prompt with no language rule at all,
    and answered Spanish users in English. The locale must reach the session's instructions."""
    session = build_realtime_session_update(_settings(), "es")["session"]
    assert "'es'" in session["instructions"]

    english = build_realtime_session_update(_settings(), "en")["session"]
    assert "'en'" in english["instructions"]
    assert english["instructions"] != session["instructions"]


def test_transcription_language_follows_the_locale() -> None:
    """The INPUT transcriber is a separate knob from the spoken output language, and it takes a
    bare ISO-639-1 code — a full `es-MX` tag is not accepted."""
    session = build_realtime_session_update(_settings(), "es-MX")["session"]
    assert session["input_audio_transcription"]["language"] == "es"

    english = build_realtime_session_update(_settings(), "en")["session"]
    assert english["input_audio_transcription"]["language"] == "en"


def test_includes_all_registered_tools() -> None:
    session = build_realtime_session_update(_settings(), "es")["session"]
    tool_names = {t["name"] for t in session["tools"]}
    assert {"render_price_chart", "get_news", "get_watchlist", "get_notes"} <= tool_names
    assert "get_market_data" not in tool_names
    # Flat function-tool shape (name at top level), not Chat-Completions nesting.
    assert all(t["type"] == "function" for t in session["tools"])


def test_audio_is_pcm16_both_directions() -> None:
    session = build_realtime_session_update(_settings(), "es")["session"]
    assert session["input_audio_format"] == "pcm16"
    assert session["output_audio_format"] == "pcm16"


def test_voice_from_settings() -> None:
    session = build_realtime_session_update(_settings(), "es")["session"]
    assert session["voice"] == "verse"


def test_server_vad_turn_detection() -> None:
    session = build_realtime_session_update(_settings(), "es")["session"]
    assert session["turn_detection"]["type"] == "server_vad"


def test_modalities_text_and_audio() -> None:
    session = build_realtime_session_update(_settings(), "es")["session"]
    assert set(session["modalities"]) == {"text", "audio"}
