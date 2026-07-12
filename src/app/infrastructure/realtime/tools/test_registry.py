"""Tests for the realtime tool registry: schema shape, allowlist, arg validation, dispatch.

Every handler is exercised against a fake container whose `get_*` accessors return
`AsyncMock`/`Mock` ports, so no real network/DB/LLM is touched. The security-critical
assertions come first: unknown tools are rejected, malformed args are rejected, and the
JWT-derived `user_id` is what reaches the handler (never a value smuggled in arguments).
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.domain.market.entities import AssetClass, Instrument, PriceCandle, PriceSeries
from app.domain.notes.entities import Note
from app.domain.signals.entities import ImpactClass, Signal
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.infrastructure.realtime.tools import (
    ToolNotFoundError,
    build_realtime_tool_schemas,
    dispatch_realtime_tool,
    is_registered_tool,
    validate_tool_args,
)

_INSTRUMENT = Instrument(
    symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.STOCK, currency="USD"
)


def _fake_container(**providers: Any) -> Any:
    """Build a stand-in container exposing only the `get_*` accessors handlers call."""
    container = SimpleNamespace(_settings=SimpleNamespace(default_locale="en"))
    for name, value in providers.items():
        setattr(container, name, Mock(return_value=value))
    return container


# --- schema shape -----------------------------------------------------------------


def test_schemas_use_flat_function_shape() -> None:
    schemas = build_realtime_tool_schemas()

    names = {s["name"] for s in schemas}
    assert names == {
        "get_market_data",
        "get_news",
        "list_signals",
        "generate_signal",
        "get_watchlist",
        "get_notes",
    }
    for schema in schemas:
        # Flat shape the Realtime session mint expects — NOT nested under "function".
        assert schema["type"] == "function"
        assert "function" not in schema
        assert isinstance(schema["name"], str)
        assert isinstance(schema["description"], str)
        assert schema["parameters"]["type"] == "object"


# --- allowlist + arg validation (security first) -----------------------------------


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(ToolNotFoundError):
        validate_tool_args("drop_tables", {})
    assert is_registered_tool("drop_tables") is False


async def test_unknown_tool_never_dispatches() -> None:
    with pytest.raises(ToolNotFoundError):
        await dispatch_realtime_tool(_fake_container(), "rm_rf", {}, "user-1")


def test_malformed_args_rejected_missing_required() -> None:
    with pytest.raises(ValidationError):
        validate_tool_args("get_market_data", {})  # symbol required


def test_malformed_args_rejected_extra_field() -> None:
    with pytest.raises(ValidationError):
        validate_tool_args("get_market_data", {"symbol": "AAPL", "evil": True})


def test_malformed_args_rejected_out_of_range() -> None:
    with pytest.raises(ValidationError):
        validate_tool_args("get_market_data", {"symbol": "AAPL", "days": 9999})


# --- dispatch delegates to the real ports with the JWT user_id ---------------------


async def test_get_market_data_dispatches_to_provider() -> None:
    provider = Mock()
    provider.get_last_price = AsyncMock(return_value=201.5)
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
    container = _fake_container(
        get_instrument_universe=universe, get_market_data_provider=provider
    )

    output = await dispatch_realtime_tool(
        container, "get_market_data", {"symbol": "aapl"}, "user-1"
    )

    provider.get_last_price.assert_awaited_once_with(_INSTRUMENT)
    assert output["symbol"] == "AAPL"
    assert output["last_price"] == 201.5
    assert output["series"][0]["close"] == 200.0


async def test_get_news_dispatches_to_provider() -> None:
    provider = Mock()
    provider.fetch_news = AsyncMock(
        return_value=[
            SimpleNamespace(
                title="Apple beats",
                summary="Q3 results",
                source="Reuters",
                url="https://x",
                published_at=datetime(2026, 7, 1, tzinfo=UTC),
            )
        ]
    )
    container = _fake_container(get_news_provider=provider)

    output = await dispatch_realtime_tool(
        container, "get_news", {"symbol": "AAPL", "limit": 3}, "user-1"
    )

    provider.fetch_news.assert_awaited_once_with(symbols=["AAPL"], limit=3)
    assert output["count"] == 1
    assert output["items"][0]["source"] == "Reuters"


async def test_list_signals_dispatches_to_repository() -> None:
    signal = Signal(
        id="sig-1",
        instrument_symbol="AAPL",
        impact_class=ImpactClass.POSITIVE,
        confidence=0.8,
        evidence=[],
        disclaimer="not advice",
        thesis="Bullish.",
    )
    repo = Mock()
    repo.list_for_instrument = AsyncMock(return_value=[signal])
    container = _fake_container(get_signal_repository=repo)

    output = await dispatch_realtime_tool(
        container, "list_signals", {"symbol": "aapl"}, "user-1"
    )

    repo.list_for_instrument.assert_awaited_once_with("AAPL")
    assert output["count"] == 1
    assert output["signals"][0]["impact_class"] == "positive"


async def test_generate_signal_rejects_user_id_in_arguments() -> None:
    """A `user_id` smuggled into arguments must be rejected (extra=forbid), never used."""
    with pytest.raises(ValidationError):
        validate_tool_args("generate_signal", {"symbol": "AAPL", "user_id": "attacker"})


async def test_generate_signal_valid_dispatch() -> None:
    signal = Signal(
        id="sig-3",
        instrument_symbol="AAPL",
        impact_class=ImpactClass.NEUTRAL,
        confidence=0.5,
        evidence=[],
        disclaimer="not advice",
        thesis="Flat.",
    )
    use_case = Mock()
    use_case.execute = AsyncMock(return_value=signal)
    container = _fake_container(get_generate_signal_use_case=use_case)

    output = await dispatch_realtime_tool(
        container, "generate_signal", {"symbol": "aapl"}, "jwt-user-9"
    )

    use_case.execute.assert_awaited_once_with("AAPL", "en")
    assert output["id"] == "sig-3"
    assert output["impact_class"] == "neutral"


# --- user-scoped tools: scope by JWT user_id, never a model-supplied id -------------


async def test_get_watchlist_dispatches_with_jwt_user_id() -> None:
    watchlist = Watchlist(id="wl-1", user_id="jwt-user-7", name="Tech")
    repo = Mock()
    repo.list_for_user = AsyncMock(return_value=[watchlist])
    repo.list_items = AsyncMock(
        return_value=[WatchlistItem(id="it-1", watchlist_id="wl-1", symbol="AAPL")]
    )
    container = _fake_container(get_watchlist_repository=repo)

    output = await dispatch_realtime_tool(container, "get_watchlist", {}, "jwt-user-7")

    repo.list_for_user.assert_awaited_once_with("jwt-user-7")
    repo.list_items.assert_awaited_once_with("wl-1")
    assert output["count"] == 1
    assert output["watchlists"][0]["name"] == "Tech"
    assert output["watchlists"][0]["symbols"] == ["AAPL"]


async def test_get_watchlist_ignores_user_id_in_arguments() -> None:
    """A `user_id` smuggled into arguments must be rejected (extra=forbid), never used."""
    with pytest.raises(ValidationError):
        validate_tool_args("get_watchlist", {"user_id": "attacker"})


async def test_get_notes_dispatches_with_jwt_user_id() -> None:
    note = Note(id="n-1", user_id="jwt-user-8", body="Watch the Fed.")
    repo = Mock()
    repo.list_for_user = AsyncMock(return_value=[note])
    container = _fake_container(get_note_repository=repo)

    output = await dispatch_realtime_tool(container, "get_notes", {}, "jwt-user-8")

    repo.list_for_user.assert_awaited_once_with("jwt-user-8")
    assert output["count"] == 1
    assert output["notes"][0]["body"] == "Watch the Fed."
    assert output["notes"][0]["id"] == "n-1"


async def test_get_notes_ignores_user_id_in_arguments() -> None:
    with pytest.raises(ValidationError):
        validate_tool_args("get_notes", {"user_id": "attacker"})
