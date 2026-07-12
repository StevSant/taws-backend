import hashlib
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.realtime.client_secret_create_params import ExpiresAfter, Session

from app.domain.agents.entities import EphemeralRealtimeSession
from app.domain.agents.ports import RealtimeSessionProvider

_NO_KEY_ERROR = (
    "[OpenAIRealtimeSessionProvider] No Realtime API key configured — cannot mint an "
    "ephemeral session."
)


class OpenAIRealtimeSessionProvider(RealtimeSessionProvider):
    """`RealtimeSessionProvider` adapter backed by OpenAI's Realtime API.

    Exchanges the real (billed) Realtime API key for a short-lived `ek_*` client secret
    via `client.realtime.client_secrets.create` (the stable SDK method — NOT the
    deprecated `beta.realtime.sessions.*`). Only the ephemeral secret is placed on the
    returned `EphemeralRealtimeSession`; the real key is held on the private
    `AsyncOpenAI` client and never surfaced to callers.

    Missing-key guard: unlike `OpenAIProvider`/`OpenAIEmbeddings` (which degrade to a
    placeholder so unauthenticated chat still works), a realtime mint has no safe
    placeholder — there is no ephemeral secret to hand the browser — so it raises. The
    DI container is what decides whether to build this adapter at all (returns `None`
    when unconfigured), so this raise only fires on a real misconfiguration.
    """

    def __init__(self, api_key: str | None) -> None:
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None

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
        if self._client is None:
            raise RuntimeError(_NO_KEY_ERROR)

        # Built as plain dicts (the SDK params are TypedDicts) and cast to the SDK's
        # param types so the call is type-checked at the boundary without pulling vendor
        # types into the rest of the codebase.
        session_config = cast(
            Session,
            {
                "type": "realtime",
                "model": model,
                "instructions": instructions,
                "tools": tools,
                "audio": {"output": {"voice": voice}},
            },
        )
        expires_after = cast(
            ExpiresAfter, {"anchor": "created_at", "seconds": expires_in_seconds}
        )
        response = await self._client.realtime.client_secrets.create(
            expires_after=expires_after,
            session=session_config,
            extra_headers={"OpenAI-Safety-Identifier": _hash_user_id(user_id)},
        )

        return EphemeralRealtimeSession(
            client_secret=response.value,
            model=_response_model(response, fallback=model),
            expires_at=response.expires_at,
            tools=tools,
        )


def _hash_user_id(user_id: str) -> str:
    """Stable, non-reversible id for OpenAI abuse tracing — never sends the raw user id."""
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()


def _response_model(response: Any, *, fallback: str) -> str:
    """Read the minted session's model, falling back to the requested one if absent."""
    session = getattr(response, "session", None)
    model = getattr(session, "model", None) if session is not None else None
    return model if isinstance(model, str) else fallback
