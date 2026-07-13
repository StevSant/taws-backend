from typing import Any

from app.core.config import Settings
from app.infrastructure.realtime.realtime_instructions import REALTIME_INSTRUCTIONS
from app.infrastructure.realtime.tools import build_realtime_tool_schemas
from app.infrastructure.realtime.ws.openai_events import (
    AUDIO_FORMAT_PCM16,
    CLIENT_SESSION_UPDATE,
)


def build_realtime_session_update(settings: Settings) -> dict[str, Any]:
    """Build the single `session.update` the WS proxy sends after `session.created`.

    Pure function (config in, dict out — no OpenAI, no socket). Configures the session
    with the SAME server-authored tool schemas + instructions the WebRTC path uses (so
    the browser never chooses which tools the model can call), plus the pcm16 audio
    format both ways, the configured voice, `server_vad` turn detection (OpenAI
    auto-commits turns — the browser just streams mic audio), and text+audio modalities.
    """
    return {
        "type": CLIENT_SESSION_UPDATE,
        "session": {
            "instructions": REALTIME_INSTRUCTIONS,
            "tools": build_realtime_tool_schemas(),
            "input_audio_format": AUDIO_FORMAT_PCM16,
            "output_audio_format": AUDIO_FORMAT_PCM16,
            "voice": settings.openai_realtime_voice,
            "turn_detection": {"type": "server_vad"},
            "modalities": ["text", "audio"],
        },
    }
