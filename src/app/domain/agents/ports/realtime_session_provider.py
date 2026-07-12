from abc import ABC, abstractmethod

from app.domain.agents.entities import EphemeralRealtimeSession


class RealtimeSessionProvider(ABC):
    """Port for minting short-lived OpenAI Realtime sessions for browser WebRTC.

    The adapter holds the real (billed) Realtime API key and exchanges it for an
    ephemeral `ek_*` client secret scoped to one session. Only that ephemeral secret
    is returned to the caller (and, in turn, the browser) — the real key never leaves
    the backend. This keeps the vendor SDK/REST call in `infrastructure/`, so nothing
    in `application/`/`api/` depends on OpenAI directly.
    """

    @abstractmethod
    async def mint_ephemeral_session(
        self,
        *,
        user_id: str,
        model: str,
        voice: str,
        instructions: str,
        tools: list[dict],
        expires_in_seconds: int,
    ) -> EphemeralRealtimeSession:
        """Mint an ephemeral Realtime session and return its `ek_*` client secret.

        `user_id` is the authenticated caller (used for abuse tracing, e.g. a hashed
        safety identifier) — never trusted from the browser. `tools` is the exact
        server-authored tool schema list to bind to the session. Raises on a failed
        mint; callers translate that into an HTTP error.
        """
        raise NotImplementedError
