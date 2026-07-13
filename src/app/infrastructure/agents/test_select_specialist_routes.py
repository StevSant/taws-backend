import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Send
from pydantic import ValidationError

from app.infrastructure.agents import RouteDecision
from app.infrastructure.agents.select_specialist_routes import select_specialist_routes
from app.infrastructure.agents.supervisor_route import SupervisorRoute


def test_single_route_keeps_direct_specialist_path() -> None:
    selected = select_specialist_routes(
        {"messages": [], "routes": ["quant"], "contributions": []}
    )

    assert selected == "quant"


def test_multiple_routes_fan_out_to_contributors() -> None:
    selected = select_specialist_routes(
        {
            "messages": [HumanMessage(content="question")],
            "routes": ["quant", "analyst"],
            "locale": "es",
            "contributions": [],
        }
    )

    assert isinstance(selected, list)
    assert all(isinstance(item, Send) for item in selected)
    assert [item.arg["contributor_route"] for item in selected] == ["quant", "analyst"]
    assert all(item.arg["messages"][0].content == "question" for item in selected)
    assert all(item.arg["routes"] == ["quant", "analyst"] for item in selected)


def test_route_decision_rejects_duplicates_and_more_than_three_routes() -> None:
    with pytest.raises(ValidationError):
        RouteDecision(
            routes=[SupervisorRoute.QUANT, SupervisorRoute.QUANT], reason="duplicate"
        )

    with pytest.raises(ValidationError):
        RouteDecision(
            routes=[
                SupervisorRoute.QUANT,
                SupervisorRoute.ANALYST,
                SupervisorRoute.MACRO,
                SupervisorRoute.SENTIMENT,
            ],
            reason="too many",
        )


def test_scope_routes_cannot_run_with_market_specialists() -> None:
    with pytest.raises(ValidationError):
        RouteDecision(
            routes=[SupervisorRoute.OUT_OF_SCOPE, SupervisorRoute.QUANT],
            reason="unsafe mix",
        )
