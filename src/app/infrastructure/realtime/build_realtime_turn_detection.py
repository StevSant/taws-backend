from typing import Any

from app.core.config import Settings


def build_realtime_turn_detection(settings: Settings) -> dict[str, Any]:
    """Build the tuned `server_vad` turn-detection object shared by both Realtime transports.

    Replaces the bare `{"type": "server_vad"}` both paths used to send. Every knob comes from
    `Settings` (never hardcoded): a deterministic activation threshold and end-of-turn silence
    window, plus `create_response`/`interrupt_response` so the model reliably answers at
    end-of-turn and the user can barge in — which is what stops the voice agent talking over
    (and responding to) itself.

    The OBJECT is identical for both transports; only its placement differs — the GA
    `client_secrets.create` mint nests it under `audio.input.turn_detection`, while the WS
    `session.update` builder puts it at the session top level.
    """
    return {
        "type": "server_vad",
        "threshold": settings.openai_realtime_vad_threshold,
        "silence_duration_ms": settings.openai_realtime_vad_silence_ms,
        "create_response": settings.openai_realtime_vad_create_response,
        "interrupt_response": settings.openai_realtime_vad_interrupt_response,
    }
