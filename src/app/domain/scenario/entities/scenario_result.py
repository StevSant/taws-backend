from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.consequence.entities import ConsequenceChain
from app.domain.scenario.entities.scenario_asset_class_impact import ScenarioAssetClassImpact
from app.domain.scenario.entities.scenario_consensus import (
    ScenarioAgentContribution,
    ScenarioConsensus,
)
from app.domain.scenario.entities.scenario_spec import ScenarioSpec


@dataclass(slots=True)
class ScenarioResult:
    """The Scenario Simulation graph's final, persisted output (issue #12) — the Analyst-
    style synthesis of a "what-if" scenario's likely market impact.

    Written by the Synthesis step (`application/scenario/use_cases/
    synthesize_scenario_result.py`) and gated by the Compliance step (`ReviewCompliance`,
    same "reject rather than silently persist" contract as `Signal`/`Briefing`) before
    `ScenarioRepository.create(...)` persists it. `disclaimer` is the same product
    invariant every other specialist output carries. No trading/execution fields exist.

    `consequence_chain` embeds the full causal chain produced for this scenario rather
    than referencing it by id: `ConsequenceChain` is deliberately never persisted on its
    own (see its docstring — "chains are generated on demand"), so a `ScenarioResult` is
    the only place a specific run's causal chain is durably recorded.

    `locale` is the language `title`/`narrative`/`recommended_actions` were written in, and
    is part of the freshness cache key for PRESET runs — `(spec.preset_id, locale)`, issue
    #29. Free-form runs have no `preset_id` and are therefore never cached (a free-text
    scenario has no stable key to cache under); they still record their locale.

    `author_id` scopes visibility (migration 0025): `None` means a global/shared run (every
    preset run, plus chat-tool runs) that any authenticated user can list; a set `author_id`
    means a FREE-FORM run private to the user who typed it, so their own words don't leak
    into everyone else's "Mis escenarios". See `SupabaseScenarioRepository.list_recent`.
    """

    id: str
    spec: ScenarioSpec
    title: str
    narrative: str
    impact_map: list[ScenarioAssetClassImpact]
    consequence_chain: ConsequenceChain
    recommended_actions: list[str]
    disclaimer: str
    locale: str = ""
    author_id: str | None = None
    agent_contributions: list[ScenarioAgentContribution] = field(default_factory=list)
    consensus: ScenarioConsensus | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
