from typing import Any

from app.core.config import Settings
from app.infrastructure.realtime.build_realtime_instructions import build_realtime_instructions
from app.infrastructure.realtime.build_realtime_turn_detection import (
    build_realtime_turn_detection,
)
from app.infrastructure.realtime.tools import build_realtime_tool_schemas
from app.infrastructure.realtime.transcription_language import transcription_language
from app.infrastructure.realtime.ws.openai_events import (
    AUDIO_FORMAT_PCM16,
    CLIENT_SESSION_UPDATE,
)


def build_realtime_session_update(settings: Settings, locale: str) -> dict[str, Any]:
    """Build the single `session.update` the WS proxy sends after `session.created`.

    Pure function (config in, dict out — no OpenAI, no socket). Configures the session
    with the SAME server-authored tool schemas + instructions the WebRTC path uses (so
    the browser never chooses which tools the model can call), plus the pcm16 audio
    format both ways, the configured voice, `server_vad` turn detection (OpenAI
    auto-commits turns — the browser just streams mic audio), and text+audio modalities.

    `locale` pins both the language the agent SPEAKS (via `build_realtime_instructions`) and
    the language the input transcriber expects. This transport previously sent the bare
    English `REALTIME_INSTRUCTIONS` with no language rule and no `input_audio_transcription`
    block at all — so a Spanish user's voice session had nothing, anywhere, telling it to
    answer in Spanish, and it simply mirrored the language of its English persona and English
    tool results.
    """
    return {
        "type": CLIENT_SESSION_UPDATE,
        "session": {
            "instructions": build_realtime_instructions(locale),
            "tools": build_realtime_tool_schemas(),
            "input_audio_format": AUDIO_FORMAT_PCM16,
            "output_audio_format": AUDIO_FORMAT_PCM16,
            "input_audio_transcription": {
                "model": "gpt-4o-mini-transcribe",
                "language": transcription_language(locale),
            },
            "voice": settings.openai_realtime_voice,
            # Tuned server_vad (Settings-driven), replacing the bare `{"type": "server_vad"}`:
            # deterministic end-of-turn detection + barge-in so the agent stops talking over
            # itself. `temperature` (valid on this beta `session.update` shape, unlike the GA
            # mint) keeps spoken replies focused. Both target the voice self-response loop.
            "temperature": settings.openai_realtime_temperature,
            "turn_detection": build_realtime_turn_detection(settings),
            "modalities": ["text", "audio"],
        },
    }
