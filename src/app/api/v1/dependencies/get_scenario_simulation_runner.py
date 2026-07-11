from typing import Annotated

from fastapi import Depends

from app.core.di import Container, get_container
from app.infrastructure.agents.scenario import ScenarioSimulationRunner


def get_scenario_simulation_runner(
    container: Annotated[Container, Depends(get_container)],
) -> ScenarioSimulationRunner:
    """FastAPI dependency resolving the cached Scenario Simulation graph runner.

    Same composed-use-case resolution shape as `get_generate_consequence_chain_use_case.py`
    (resolves the fully wired object from `Container`, not individual ports).
    """
    return container.get_scenario_simulation_runner()
