"""Contract test for the `RealtimeSessionProvider` port via an in-memory Fake.

Pins the port's shape (keyword-only `mint_ephemeral_session`, returns an
`EphemeralRealtimeSession` carrying only the ephemeral `ek_*` secret) independently of
the OpenAI adapter, so `application`/`api` code and other adapters can rely on it.
"""

from app.domain.agents.entities import EphemeralRealtimeSession
from app.domain.agents.ports import RealtimeSessionProvider


class _FakeRealtimeSessionProvider(RealtimeSessionProvider):
    """Records the mint call args and returns a canned ephemeral session."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def mint_ephemeral_session(
        self,
        *,
        user_id: str,
        model: str,
        voice: str,
        instructions: str,
        tools: list[dict],
        expires_in_seconds: int,
        transcription_language: str,
    ) -> EphemeralRealtimeSession:
        self.calls.append(
            {
                "user_id": user_id,
                "model": model,
                "voice": voice,
                "instructions": instructions,
                "tools": tools,
                "expires_in_seconds": expires_in_seconds,
                "transcription_language": transcription_language,
            }
        )
        return EphemeralRealtimeSession(
            client_secret="ek_fake_123",
            model=model,
            expires_at=1_700_000_000 + expires_in_seconds,
            tools=tools,
        )


async def test_fake_mint_returns_ephemeral_session_and_records_args() -> None:
    provider = _FakeRealtimeSessionProvider()
    tools = [{"type": "function", "name": "get_market_data"}]

    session = await provider.mint_ephemeral_session(
        user_id="user-1",
        model="gpt-realtime-2.1-mini",
        voice="alloy",
        instructions="You are TAWS voice.",
        tools=tools,
        expires_in_seconds=600,
        transcription_language="es",
    )

    assert isinstance(session, EphemeralRealtimeSession)
    assert session.client_secret == "ek_fake_123"
    assert session.model == "gpt-realtime-2.1-mini"
    assert session.expires_at == 1_700_000_000 + 600
    assert session.tools == tools
    assert provider.calls[0]["user_id"] == "user-1"
    assert provider.calls[0]["expires_in_seconds"] == 600
    assert provider.calls[0]["transcription_language"] == "es"


def test_entity_is_frozen() -> None:
    session = EphemeralRealtimeSession(client_secret="ek_x", model="m", expires_at=1, tools=[])
    try:
        session.client_secret = "leak"  # type: ignore[misc]
    except (AttributeError, TypeError):
        return
    raise AssertionError("EphemeralRealtimeSession must be immutable (frozen)")
