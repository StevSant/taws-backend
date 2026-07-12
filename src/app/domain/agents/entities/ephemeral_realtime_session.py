from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EphemeralRealtimeSession:
    """A minted, short-lived OpenAI Realtime session for browser-side WebRTC.

    `client_secret` is the ephemeral `ek_*` token the browser uses to open its own
    WebRTC connection to OpenAI — it is the ONLY secret that ever leaves the backend.
    The real (billed) Realtime API key stays server-side and is never placed on this
    entity. `expires_at` is a Unix epoch second at which `client_secret` stops working;
    the browser must re-mint after that. `tools` is the exact server-authored tool
    schema list the session was minted with (echoed back so the caller can surface the
    allowlist it will honor on `/chat/realtime/tool`), never a browser-supplied list.
    """

    client_secret: str
    model: str
    expires_at: int
    tools: list[dict] = field(default_factory=list)
