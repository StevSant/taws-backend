"""Scenario Simulation application layer (issue #12): the "what-if" market-scenario
pipeline orchestrating Intake -> Context gathering -> Causal chain -> Quantification ->
Synthesis -> Compliance.

Every step reuses an existing reusable use case rather than reimplementing it:
`GenerateConsequenceChain` (issue #8) for the causal chain, `ComputeMarketStats`/
`ComputeEventStudy` (issue #7) for quantification, `ReviewCompliance` (issue #9) as the
final gate before persistence, and `FindHistoricalAnalogs` (issue #15) for
`[análogo histórico]`-tagged context. The graph wiring itself lives in
`infrastructure/agents/scenario/` (LangGraph is a vendor/framework concern, kept out of
this layer per `backend/CLAUDE.md`'s hexagonal rule).
"""

from app.application.scenario.invalid_scenario_intake_error import InvalidScenarioIntakeError
from app.application.scenario.scenario_synthesis_unavailable_error import (
    ScenarioSynthesisUnavailableError,
)
from app.application.scenario.scenario_unavailable_message import scenario_unavailable_message
from app.application.scenario.unknown_preset_error import UnknownPresetError

__all__ = [
    "InvalidScenarioIntakeError",
    "ScenarioSynthesisUnavailableError",
    "UnknownPresetError",
    "scenario_unavailable_message",
]
