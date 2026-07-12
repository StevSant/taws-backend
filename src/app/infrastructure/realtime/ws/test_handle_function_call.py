"""Tests for `handle_realtime_function_call` — server-side tool dispatch for the WS proxy.

When OpenAI asks to call a tool, the proxy runs it IN-PROCESS (reusing the registry) with
the JWT `user_id` and returns the OpenAI messages to send back:
`[conversation.item.create{function_call_output}, response.create]`. A tool error must
still come back as a `function_call_output` carrying `{error: ...}` (never raise), so the
model can recover verbally — same contract as the HTTP `/realtime/tool` endpoint.
"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.domain.signals.entities import ImpactClass, Signal
from app.infrastructure.realtime.ws.handle_function_call import (
    handle_realtime_function_call,
)


def _fake_container(**providers: Any) -> Any:
    container = SimpleNamespace(_settings=SimpleNamespace(default_locale="en"))
    for name, value in providers.items():
        setattr(container, name, Mock(return_value=value))
    return container


def _output_payload(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """The `output` string on the function_call_output item, parsed back to a dict."""
    item = messages[0]["item"]
    return json.loads(item["output"])


@pytest.mark.asyncio
async def test_valid_call_returns_output_and_response_create() -> None:
    signal = Signal(
        id="sig-1",
        instrument_symbol="AAPL",
        impact_class=ImpactClass.POSITIVE,
        confidence=0.7,
        evidence=[],
        disclaimer="not advice",
        thesis="Bullish.",
    )
    use_case = Mock()
    use_case.execute = AsyncMock(return_value=signal)
    container = _fake_container(get_generate_signal_use_case=use_case)

    messages = await handle_realtime_function_call(
        container,
        name="generate_signal",
        call_id="call-9",
        arguments={"symbol": "aapl"},
        user_id="jwt-user-1",
    )

    assert len(messages) == 2
    create, response = messages
    assert create["type"] == "conversation.item.create"
    assert create["item"]["type"] == "function_call_output"
    assert create["item"]["call_id"] == "call-9"
    assert response == {"type": "response.create"}
    assert _output_payload(messages)["id"] == "sig-1"
    # user_id comes from the JWT, positionally — the use case never sees a client id.
    use_case.execute.assert_awaited_once_with("AAPL", "en")


@pytest.mark.asyncio
async def test_user_scoped_tool_scopes_to_jwt_user_id() -> None:
    repo = Mock()
    repo.list_for_user = AsyncMock(return_value=[])
    container = _fake_container(get_watchlist_repository=repo)

    await handle_realtime_function_call(
        container,
        name="get_watchlist",
        call_id="c4",
        arguments={},
        user_id="jwt-user-1",
    )

    # The user-scoped tool is scoped by the JWT subject, never a client-supplied value.
    repo.list_for_user.assert_awaited_once_with("jwt-user-1")


@pytest.mark.asyncio
async def test_injected_user_id_in_arguments_is_rejected_not_used() -> None:
    """A `user_id` smuggled into arguments must be rejected as bad args, never dispatched.

    The tool arg models forbid extra fields, so the injected id can't even reach the
    handler — it surfaces as a recoverable error output instead of scoping to the attacker.
    """
    repo = Mock()
    repo.list_for_user = AsyncMock(return_value=[])
    container = _fake_container(get_watchlist_repository=repo)

    messages = await handle_realtime_function_call(
        container,
        name="get_watchlist",
        call_id="c4",
        arguments={"user_id": "attacker"},
        user_id="jwt-user-1",
    )

    assert "error" in _output_payload(messages)
    repo.list_for_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_tool_returns_recoverable_error_output() -> None:
    messages = await handle_realtime_function_call(
        _fake_container(),
        name="drop_tables",
        call_id="c1",
        arguments={},
        user_id="jwt-user-1",
    )

    assert len(messages) == 2
    assert messages[1] == {"type": "response.create"}
    assert messages[0]["item"]["type"] == "function_call_output"
    assert messages[0]["item"]["call_id"] == "c1"
    assert "error" in _output_payload(messages)


@pytest.mark.asyncio
async def test_bad_arguments_returns_recoverable_error_output() -> None:
    messages = await handle_realtime_function_call(
        _fake_container(),
        name="get_market_data",
        call_id="c2",
        arguments={"evil": 1},
        user_id="jwt-user-1",
    )

    assert "error" in _output_payload(messages)
    assert messages[1] == {"type": "response.create"}


@pytest.mark.asyncio
async def test_tool_handler_exception_returns_recoverable_error_output() -> None:
    """A handler that blows up mid-dispatch must still yield an error output, not raise."""
    universe = Mock()
    universe.by_symbol = Mock(return_value=None)  # unknown instrument -> handler raises
    container = _fake_container(get_instrument_universe=universe)

    messages = await handle_realtime_function_call(
        container,
        name="get_market_data",
        call_id="c3",
        arguments={"symbol": "ZZZZ"},
        user_id="jwt-user-1",
    )

    assert "error" in _output_payload(messages)
