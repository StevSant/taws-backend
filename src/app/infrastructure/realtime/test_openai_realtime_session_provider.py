"""Tests for `OpenAIRealtimeSessionProvider` with a mocked OpenAI SDK client.

No network and no key is needed: the SDK `AsyncOpenAI` client is replaced with a fake
whose `realtime.client_secrets.create` records the request and returns a canned
`ek_*` response. Asserts the model/voice/tools/ttl are passed through, the ephemeral
secret is mapped onto the entity, a hashed (never raw) safety identifier is sent, and —
critically — the real API key is NEVER exposed on the returned DTO.
"""

import hashlib
from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.agents.entities import EphemeralRealtimeSession
from app.infrastructure.realtime import OpenAIRealtimeSessionProvider

_REAL_KEY = "sk-real-secret-key-do-not-leak"


class _FakeClientSecrets:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.create_calls.append(kwargs)
        return SimpleNamespace(
            value="ek_minted_abc",
            expires_at=1_700_000_600,
            session=SimpleNamespace(model="gpt-realtime-2.1-mini"),
        )


class _FakeRealtime:
    def __init__(self, client_secrets: _FakeClientSecrets) -> None:
        self.client_secrets = client_secrets


class _FakeAsyncOpenAI:
    def __init__(self, client_secrets: _FakeClientSecrets) -> None:
        self.realtime = _FakeRealtime(client_secrets)


def _build_provider() -> tuple[OpenAIRealtimeSessionProvider, _FakeClientSecrets]:
    fake_secrets = _FakeClientSecrets()
    provider = OpenAIRealtimeSessionProvider(api_key=_REAL_KEY)
    # Swap the SDK client for the fake so no network/key is used.
    provider._client = _FakeAsyncOpenAI(fake_secrets)  # type: ignore[assignment]
    return provider, fake_secrets


_TOOLS = [
    {
        "type": "function",
        "name": "get_market_data",
        "description": "Get the latest price.",
        "parameters": {"type": "object", "properties": {}},
    }
]


async def test_mint_returns_ephemeral_session_from_client_secret() -> None:
    provider, _ = _build_provider()

    session = await provider.mint_ephemeral_session(
        user_id="user-42",
        model="gpt-realtime-2.1-mini",
        voice="alloy",
        instructions="You are TAWS voice.",
        tools=_TOOLS,
        expires_in_seconds=600,
    )

    assert isinstance(session, EphemeralRealtimeSession)
    assert session.client_secret == "ek_minted_abc"
    assert session.model == "gpt-realtime-2.1-mini"
    assert session.expires_at == 1_700_000_600
    assert session.tools == _TOOLS


async def test_mint_passes_model_voice_tools_and_ttl_through() -> None:
    provider, secrets = _build_provider()

    await provider.mint_ephemeral_session(
        user_id="user-42",
        model="gpt-realtime-2.1-mini",
        voice="verse",
        instructions="Custom instructions.",
        tools=_TOOLS,
        expires_in_seconds=900,
    )

    call = secrets.create_calls[0]
    assert call["expires_after"] == {"anchor": "created_at", "seconds": 900}
    session_arg = call["session"]
    assert session_arg["type"] == "realtime"
    assert session_arg["model"] == "gpt-realtime-2.1-mini"
    assert session_arg["instructions"] == "Custom instructions."
    assert session_arg["tools"] == _TOOLS
    assert session_arg["tool_choice"] == "required"
    assert session_arg["audio"]["input"]["transcription"]["model"] == "gpt-4o-mini-transcribe"
    assert session_arg["audio"]["output"]["voice"] == "verse"


async def test_mint_sends_hashed_safety_identifier_never_raw_user_id() -> None:
    provider, secrets = _build_provider()

    await provider.mint_ephemeral_session(
        user_id="user-42",
        model="gpt-realtime-2.1-mini",
        voice="alloy",
        instructions="x",
        tools=[],
        expires_in_seconds=600,
    )

    call = secrets.create_calls[0]
    headers = call["extra_headers"]
    expected = hashlib.sha256(b"user-42").hexdigest()
    assert headers["OpenAI-Safety-Identifier"] == expected
    assert "user-42" not in headers["OpenAI-Safety-Identifier"]


async def test_real_key_never_appears_on_returned_session() -> None:
    provider, _ = _build_provider()

    session = await provider.mint_ephemeral_session(
        user_id="user-42",
        model="gpt-realtime-2.1-mini",
        voice="alloy",
        instructions="x",
        tools=[],
        expires_in_seconds=600,
    )

    assert _REAL_KEY not in session.client_secret
    assert _REAL_KEY not in str(session)
    assert session.client_secret.startswith("ek_")


async def test_missing_key_raises() -> None:
    provider = OpenAIRealtimeSessionProvider(api_key=None)

    with pytest.raises(RuntimeError):
        await provider.mint_ephemeral_session(
            user_id="user-42",
            model="gpt-realtime-2.1-mini",
            voice="alloy",
            instructions="x",
            tools=[],
            expires_in_seconds=600,
        )
