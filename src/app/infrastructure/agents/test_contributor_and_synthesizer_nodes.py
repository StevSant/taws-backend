from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.infrastructure.agents import Contribution, RouteDecision, build_supervisor_graph
from app.infrastructure.agents.contributor_node import ANALYSIS_MAX_CHARS, build_contributor_node
from app.infrastructure.agents.supervisor_route import SupervisorRoute
from app.infrastructure.agents.synthesizer_node import build_synthesizer_node

_TRUNCATION_MARKER = "... [truncated]"


class _FakeTool:
    """Minimal stand-in for a bound tool: the dedupe logic only reads `.name`."""

    def __init__(self, name: str) -> None:
        self.name = name


class _StructuredContributionModel:
    async def ainvoke(self, messages: list[Any], config: dict[str, Any]) -> Contribution:
        return Contribution.model_validate(
            {
                "agent": "quant",
                "summary": "BTC fell less than BNB.",
                "findings": [
                    {
                        "claim": "BTC returned -33%.",
                        "source": {
                            "kind": "quant",
                            "metric": "six-month return",
                            "value": "-33%",
                        },
                    }
                ],
            }
        )


class _ContributorModel:
    async def ainvoke(self, messages: list[Any], config: dict[str, Any]) -> AIMessage:
        assert "internal_contributor" in config["tags"]
        return AIMessage(content="Computed BTC and BNB performance.")

    def with_structured_output(self, schema: type[Contribution]) -> _StructuredContributionModel:
        assert schema is Contribution
        return _StructuredContributionModel()


class _SynthesizerModel:
    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        self.messages = messages
        return AIMessage(content="BTC had the better six-month return.")


class _GraphStructuredModel:
    def __init__(self, schema: type[Any]) -> None:
        self.schema = schema

    async def ainvoke(self, messages: list[Any], config: dict[str, Any]) -> Any:
        if self.schema is RouteDecision:
            return RouteDecision(
                routes=[SupervisorRoute.QUANT, SupervisorRoute.ANALYST],
                reason="Needs prices and news.",
            )
        return Contribution(agent="placeholder", summary="Grounded evidence.", findings=[])


class _GraphModel:
    def with_structured_output(self, schema: type[Any]) -> _GraphStructuredModel:
        return _GraphStructuredModel(schema)

    async def ainvoke(self, messages: list[Any], config: dict[str, Any] | None = None) -> AIMessage:
        is_synthesis = any(
            "Specialist contributions" in str(getattr(message, "content", ""))
            for message in messages
        )
        return AIMessage(content="Synthesized answer." if is_synthesis else "Grounded evidence.")


async def test_contributor_returns_structured_finding_without_chat_message(
    monkeypatch: Any,
) -> None:
    payloads: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "app.infrastructure.agents.contributor_node.get_stream_writer",
        lambda: payloads.append,
    )
    node = build_contributor_node(
        _ContributorModel(),  # type: ignore[arg-type]
        personas={"quant": "Quant persona"},
        tools_by_route={"quant": None},
        history_max_messages=12,
    )

    update = await node({"messages": ["compare"], "contributor_route": "quant"})

    assert "messages" not in update
    # No tools bound -> no tool evidence, so the contributor skips the extraction LLM call
    # entirely and passes the response through directly: summary is the model's text, no findings.
    assert update["contributions"][0].agent == "quant"
    assert update["contributions"][0].summary == "Computed BTC and BNB performance."
    assert update["contributions"][0].findings == []
    # The raw response prose is passed through as `analysis` even on the no-evidence fallback,
    # so the synthesizer receives the specialist's full grounded text, not just the digest.
    assert update["contributions"][0].analysis == "Computed BTC and BNB performance."
    assert [payload["event"] for payload in payloads] == ["start", "done"]


async def test_synthesizer_reads_every_contribution_and_returns_one_message(
    monkeypatch: Any,
) -> None:
    payloads: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "app.infrastructure.agents.synthesizer_node.get_stream_writer",
        lambda: payloads.append,
    )
    model = _SynthesizerModel()
    node = build_synthesizer_node(model, history_max_messages=12)  # type: ignore[arg-type]
    contributions = [
        Contribution(agent="quant", summary="BTC fell less.", findings=[]),
        Contribution(agent="analyst", summary="BTC had stronger sourced news.", findings=[]),
    ]

    update = await node(
        {
            "messages": [HumanMessage(content="compare")],
            "contributions": contributions,
            "locale": "es",
        }
    )

    assert update["messages"][0].content == "BTC had the better six-month return."
    serialized_prompt = "\n".join(str(message.content) for message in model.messages)
    assert '"agent":"quant"' in serialized_prompt
    assert '"agent":"analyst"' in serialized_prompt
    assert [payload["agent"] for payload in payloads] == ["advisor", "advisor"]


async def test_compiled_graph_fans_out_and_synthesizes_once() -> None:
    model = _GraphModel()
    graph = build_supervisor_graph(
        model,  # type: ignore[arg-type]
        model,  # type: ignore[arg-type]
        InMemorySaver(),
        4,
        12,
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Compare BTC and BNB")]},
        config={"configurable": {"thread_id": "fanout-test"}},
    )

    assert len(result["contributions"]) == 2
    assert result["messages"][-1].content == "Synthesized answer."


class _LongResponseModel:
    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, messages: list[Any], config: dict[str, Any]) -> AIMessage:
        return AIMessage(content=self._content)


async def test_contributor_truncates_analysis_past_the_ceiling(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "app.infrastructure.agents.contributor_node.get_stream_writer",
        lambda: lambda _payload: None,
    )
    long_text = "x" * (ANALYSIS_MAX_CHARS + 500)
    node = build_contributor_node(
        _LongResponseModel(long_text),  # type: ignore[arg-type]
        personas={"advisor": "Advisor persona"},
        tools_by_route={"advisor": None},
        history_max_messages=12,
    )

    update = await node({"messages": ["explain"], "contributor_route": "advisor"})

    analysis = update["contributions"][0].analysis
    assert analysis is not None
    # Capped at the ceiling plus the marker, keeping the head and flagging the cut.
    assert len(analysis) == ANALYSIS_MAX_CHARS + len(_TRUNCATION_MARKER)
    assert analysis.endswith(_TRUNCATION_MARKER)
    assert analysis.startswith("x" * 100)


def _capture_bound_tools(captured: dict[str, list[str]]) -> Any:
    async def _invoke(
        model: Any, messages: list[Any], tools: list[Any], *, agent_name: str, **kwargs: Any
    ) -> AIMessage:
        captured[agent_name] = [tool.name for tool in tools]
        return AIMessage(content="Grounded evidence.")

    return _invoke


async def test_chart_dedupe_quant_keeps_render_tools_when_selected(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "app.infrastructure.agents.contributor_node.get_stream_writer",
        lambda: lambda _payload: None,
    )
    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(
        "app.infrastructure.agents.contributor_node.invoke_with_bound_tools",
        _capture_bound_tools(captured),
    )
    render = _FakeTool("render_comparison_chart")
    tools_by_route: dict[str, Any] = {
        "quant": [render, _FakeTool("compute_return")],
        "analyst": [render, _FakeTool("fetch_news")],
    }
    node = build_contributor_node(
        _ContributorModel(),  # type: ignore[arg-type]
        personas={"quant": "Quant persona", "analyst": "Analyst persona"},
        tools_by_route=tools_by_route,
        history_max_messages=12,
    )
    base_state = {"messages": ["compare"], "routes": ["quant", "analyst"]}

    await node({**base_state, "contributor_route": "quant"})
    await node({**base_state, "contributor_route": "analyst"})

    # Quant wins the chart when selected; the other route keeps only its non-render tools.
    assert "render_comparison_chart" in captured["quant"]
    assert "render_comparison_chart" not in captured["analyst"]
    assert "fetch_news" in captured["analyst"]


async def test_chart_dedupe_first_render_route_keeps_tools_without_quant(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "app.infrastructure.agents.contributor_node.get_stream_writer",
        lambda: lambda _payload: None,
    )
    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(
        "app.infrastructure.agents.contributor_node.invoke_with_bound_tools",
        _capture_bound_tools(captured),
    )
    render = _FakeTool("render_comparison_chart")
    tools_by_route: dict[str, Any] = {
        "analyst": [render, _FakeTool("fetch_news")],
        "advisor": [render, _FakeTool("read_watchlist")],
    }
    node = build_contributor_node(
        _ContributorModel(),  # type: ignore[arg-type]
        personas={"analyst": "Analyst persona", "advisor": "Advisor persona"},
        tools_by_route=tools_by_route,
        history_max_messages=12,
    )
    # No quant selected: the FIRST route in list order holding a render_* tool keeps it.
    base_state = {"messages": ["compare"], "routes": ["analyst", "advisor"]}

    await node({**base_state, "contributor_route": "analyst"})
    await node({**base_state, "contributor_route": "advisor"})

    assert "render_comparison_chart" in captured["analyst"]
    assert "render_comparison_chart" not in captured["advisor"]
    assert "read_watchlist" in captured["advisor"]
