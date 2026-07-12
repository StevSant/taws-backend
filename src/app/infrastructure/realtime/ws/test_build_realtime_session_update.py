"""Tests for `build_realtime_session_update` — the pure `session.update` builder.

The WS proxy sends exactly one `session.update` after `session.created`, configuring the
same server-authored tools + instructions the WebRTC path uses, plus the pcm16/voice/VAD
audio settings. Pure function -> no OpenAI, no socket.
"""

from app.core.config import Settings
from app.infrastructure.realtime.realtime_instructions import REALTIME_INSTRUCTIONS
from app.infrastructure.realtime.ws.build_realtime_session_update import (
    build_realtime_session_update,
)


def _settings() -> Settings:
    return Settings(openai_realtime_voice="verse")


def test_type_is_session_update() -> None:
    assert build_realtime_session_update(_settings())["type"] == "session.update"


def test_includes_server_authored_instructions() -> None:
    session = build_realtime_session_update(_settings())["session"]
    assert session["instructions"] == REALTIME_INSTRUCTIONS


def test_includes_all_registered_tools() -> None:
    session = build_realtime_session_update(_settings())["session"]
    tool_names = {t["name"] for t in session["tools"]}
    assert {"get_market_data", "get_news", "get_watchlist", "get_notes"} <= tool_names
    # Flat function-tool shape (name at top level), not Chat-Completions nesting.
    assert all(t["type"] == "function" for t in session["tools"])


def test_audio_is_pcm16_both_directions() -> None:
    session = build_realtime_session_update(_settings())["session"]
    assert session["input_audio_format"] == "pcm16"
    assert session["output_audio_format"] == "pcm16"


def test_voice_from_settings() -> None:
    session = build_realtime_session_update(_settings())["session"]
    assert session["voice"] == "verse"


def test_server_vad_turn_detection() -> None:
    session = build_realtime_session_update(_settings())["session"]
    assert session["turn_detection"]["type"] == "server_vad"


def test_modalities_text_and_audio() -> None:
    session = build_realtime_session_update(_settings())["session"]
    assert set(session["modalities"]) == {"text", "audio"}
