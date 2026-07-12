"""Endpoint tests for `POST /api/v1/chat/realtime/session` and `.../realtime/tool`.

Drives the real FastAPI app via `TestClient` with `app.dependency_overrides`, so the
whole request path (auth gate, DI resolution, tool allowlist + validation) is exercised.
OpenAI is never touched: the session endpoint's provider is a fake mint, and the tool
endpoint's container exposes mocked ports. Security cases (503 when off, unknown tool,
malformed args, JWT-not-arguments user id) come first.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient

from app.api.v1.dependencies import get_realtime_session_provider, require_current_user
from app.api.v1.schemas import CurrentUser
from app.core.config import get_settings
from app.core.di import get_container
from app.domain.agents.entities import EphemeralRealtimeSession
from app.domain.market.entities import AssetClass, Instrument, PriceCandle, PriceSeries
from app.domain.signals.entities import ImpactClass, Signal
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.main import app

_USER = CurrentUser(id="jwt-user-1", email="voice@example.com")
_INSTRUMENT = Instrument(
    symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"
)


class _FakeSessionProvider:
    """Records the mint call and returns a canned ephemeral session (no OpenAI)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def mint_ephemeral_session(self, **kwargs: Any) -> EphemeralRealtimeSession:
        self.calls.append(kwargs)
        return EphemeralRealtimeSession(
            client_secret="ek_test_secret",
            model=kwargs["model"],
            expires_at=1_700_000_600,
            tools=kwargs["tools"],
        )


def _override_user() -> None:
    app.dependency_overrides[require_current_user] = lambda: _USER


# --- session endpoint --------------------------------------------------------------


def test_session_returns_503_when_provider_disabled() -> None:
    _override_user()
    app.dependency_overrides[get_realtime_session_provider] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/realtime/session")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_session_returns_ephemeral_secret_and_tools() -> None:
    provider = _FakeSessionProvider()
    _override_user()
    app.dependency_overrides[get_realtime_session_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/realtime/session")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["client_secret"] == "ek_test_secret"
    assert body["expires_at"] == 1_700_000_600
    tool_names = {t["name"] for t in body["tools"]}
    assert "render_price_chart" in tool_names
    assert "get_market_data" not in tool_names
    # The mint got the server-authored tools + the JWT user id (never a client value).
    assert provider.calls[0]["user_id"] == "jwt-user-1"
    assert {t["name"] for t in provider.calls[0]["tools"]} == tool_names


def test_session_omits_chart_tools_when_charts_disabled() -> None:
    provider = _FakeSessionProvider()
    settings = get_settings().model_copy(update={"charts_enabled": False})
    _override_user()
    app.dependency_overrides[get_realtime_session_provider] = lambda: provider
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/chat/realtime/session")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert all(not tool["name"].startswith("render_") for tool in response.json()["tools"])


# --- tool endpoint (security first) ------------------------------------------------


def _fake_container(**providers: Any) -> Any:
    container = SimpleNamespace(_settings=SimpleNamespace(default_locale="en"))
    for name, value in providers.items():
        setattr(container, name, Mock(return_value=value))
    return container


def _post_tool(container: Any, payload: dict[str, Any]) -> Any:
    _override_user()
    app.dependency_overrides[get_container] = lambda: container
    try:
        with TestClient(app) as client:
            return client.post("/api/v1/chat/realtime/tool", json=payload)
    finally:
        app.dependency_overrides.clear()


def test_tool_unknown_name_rejected() -> None:
    response = _post_tool(
        _fake_container(), {"call_id": "c1", "name": "drop_tables", "arguments": {}}
    )
    assert response.status_code == 400


def test_tool_malformed_arguments_rejected() -> None:
    response = _post_tool(
        _fake_container(),
        {"call_id": "c1", "name": "get_market_data", "arguments": {"evil": 1}},
    )
    assert response.status_code == 422


def test_tool_user_id_in_arguments_is_rejected_not_used() -> None:
    response = _post_tool(
        _fake_container(),
        {
            "call_id": "c1",
            "name": "generate_signal",
            "arguments": {"symbol": "AAPL", "user_id": "attacker"},
        },
    )
    assert response.status_code == 422


def test_tool_valid_dispatch_uses_jwt_user_id() -> None:
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

    response = _post_tool(
        container,
        {"call_id": "call-9", "name": "generate_signal", "arguments": {"symbol": "aapl"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["call_id"] == "call-9"
    assert body["output"]["id"] == "sig-1"
    use_case.execute.assert_awaited_once_with("AAPL", "en")


def test_tool_market_data_dispatch() -> None:
    provider = Mock()
    provider.get_last_price = AsyncMock(return_value=201.0)
    provider.get_price_series = AsyncMock(
        return_value=PriceSeries(
            symbol="AAPL",
            candles=[
                PriceCandle(
                    timestamp=datetime(2026, 7, 1, tzinfo=UTC),
                    open=1,
                    high=2,
                    low=1,
                    close=200.0,
                )
            ],
        )
    )
    universe = Mock()
    universe.by_symbol = Mock(return_value=_INSTRUMENT)
    container = _fake_container(get_instrument_universe=universe, get_market_data_provider=provider)

    response = _post_tool(
        container,
        {"call_id": "c2", "name": "get_market_data", "arguments": {"symbol": "AAPL"}},
    )

    assert response.status_code == 200
    assert response.json()["output"]["last_price"] == 201.0


def test_tool_get_watchlist_scopes_to_jwt_user_id() -> None:
    """The user-scoped tool endpoint must scope by the JWT user id, never a client value."""
    repo = Mock()
    repo.list_for_user = AsyncMock(
        return_value=[Watchlist(id="wl-1", user_id="jwt-user-1", name="Tech")]
    )
    repo.list_items = AsyncMock(
        return_value=[WatchlistItem(id="it-1", watchlist_id="wl-1", symbol="AAPL")]
    )
    container = _fake_container(get_watchlist_repository=repo)

    response = _post_tool(
        container, {"call_id": "c4", "name": "get_watchlist", "arguments": {}}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["call_id"] == "c4"
    assert body["output"]["watchlists"][0]["symbols"] == ["AAPL"]
    repo.list_for_user.assert_awaited_once_with("jwt-user-1")


def test_tool_recoverable_error_returns_structured_output_not_500() -> None:
    """A bad symbol (unknown instrument) must come back as a structured error output the
    model can recover from — never a 500."""
    universe = Mock()
    universe.by_symbol = Mock(return_value=None)
    container = _fake_container(get_instrument_universe=universe)

    response = _post_tool(
        container,
        {"call_id": "c3", "name": "get_market_data", "arguments": {"symbol": "ZZZZ"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["call_id"] == "c3"
    assert "error" in body["output"]
