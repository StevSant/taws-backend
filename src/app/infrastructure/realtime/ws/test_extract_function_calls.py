"""Tests for `extract_function_calls` — pulls function_call items from `response.done`."""

import json

from app.infrastructure.realtime.ws.extract_function_calls import extract_function_calls


def test_non_response_done_yields_nothing() -> None:
    assert extract_function_calls({"type": "response.output_audio.delta"}) == []


def test_response_done_without_function_calls_yields_nothing() -> None:
    event = {"type": "response.done", "response": {"output": [{"type": "message"}]}}
    assert extract_function_calls(event) == []


def test_extracts_function_call_with_parsed_arguments() -> None:
    event = {
        "type": "response.done",
        "response": {
            "output": [
                {
                    "type": "function_call",
                    "name": "get_market_data",
                    "call_id": "c1",
                    "arguments": json.dumps({"symbol": "AAPL"}),
                }
            ]
        },
    }
    calls = extract_function_calls(event)
    assert calls == [{"name": "get_market_data", "call_id": "c1", "arguments": {"symbol": "AAPL"}}]


def test_malformed_argument_json_degrades_to_empty_dict() -> None:
    event = {
        "type": "response.done",
        "response": {
            "output": [
                {
                    "type": "function_call",
                    "name": "get_watchlist",
                    "call_id": "c2",
                    "arguments": "{not json",
                }
            ]
        },
    }
    assert extract_function_calls(event)[0]["arguments"] == {}


def test_multiple_function_calls_all_extracted() -> None:
    event = {
        "type": "response.done",
        "response": {
            "output": [
                {"type": "function_call", "name": "a", "call_id": "1", "arguments": "{}"},
                {"type": "message"},
                {"type": "function_call", "name": "b", "call_id": "2", "arguments": "{}"},
            ]
        },
    }
    names = [c["name"] for c in extract_function_calls(event)]
    assert names == ["a", "b"]


def test_missing_response_key_yields_nothing() -> None:
    assert extract_function_calls({"type": "response.done"}) == []
