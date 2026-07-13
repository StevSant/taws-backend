from langchain_core.tools import BaseTool

from app.infrastructure.agents.scenario import ScenarioSimulationRunner
from app.infrastructure.agents.tools.run_scenario_simulation_tool import (
    build_run_scenario_simulation_tool,
)


def build_scenario_tools(
    scenario_simulation_runner: ScenarioSimulationRunner, default_locale: str
) -> list[BaseTool]:
    """Build the tools bound to the `advisor` specialist node for triggering the Scenario
    Simulation graph (issue #12) from chat.

    Safe for the unauthenticated `POST /api/v1/chat/stream` route: `ScenarioResult`s are
    not per-user data (same visibility as `Signal`s) — see `ScenarioRepository`'s
    docstring. See `Container.get_run_scenario_simulation` for where this gets wired in,
    and `build_advisor_grounding_tools.py` for the sibling tool list `advisor_tools`
    concatenates this with (kept in a separate builder since this isn't "grounding an
    answer in persisted signals", it's "trigger a whole pipeline").

    `default_locale` is only the fallback — the tool prefers the turn's locale from its injected
    `RunnableConfig` (see `resolve_tool_locale`).
    """
    return [build_run_scenario_simulation_tool(scenario_simulation_runner, default_locale)]
