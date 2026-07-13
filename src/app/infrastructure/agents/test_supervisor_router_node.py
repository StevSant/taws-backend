from typing import Any

from app.infrastructure.agents import RouteDecision, build_supervisor_router_node
from app.infrastructure.agents.supervisor_route import SupervisorRoute


class _StructuredModel:
    async def ainvoke(self, messages: list[Any], config: dict[str, Any]) -> RouteDecision:
        return RouteDecision(
            routes=[SupervisorRoute.QUANT, SupervisorRoute.ANALYST],
            reason="Needs prices and news.",
        )


class _RouterModel:
    def with_structured_output(self, schema: type[RouteDecision]) -> _StructuredModel:
        assert schema is RouteDecision
        return _StructuredModel()


async def test_router_returns_all_routes_and_clears_previous_contributions(
    monkeypatch: Any,
) -> None:
    payloads: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "app.infrastructure.agents.supervisor_router_node.get_stream_writer",
        lambda: payloads.append,
    )
    node = build_supervisor_router_node(_RouterModel(), 4)  # type: ignore[arg-type]

    update = await node({"messages": [], "contributions": ["stale"]})

    assert update["routes"] == ["quant", "analyst"]
    assert update["contributions"].value == []
    assert payloads[0]["detail"] == "Needs prices and news."
