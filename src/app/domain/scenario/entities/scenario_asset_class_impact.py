from dataclasses import dataclass

from app.domain.market.entities import AssetClass
from app.domain.scenario.entities.scenario_evidence import ScenarioEvidence
from app.domain.signals.entities import ImpactClass


@dataclass(frozen=True, slots=True)
class ScenarioAssetClassImpact:
    """One entry in a `ScenarioResult.impact_map`: the Synthesis step's call on how one
    asset class is likely affected by the scenario, with its cited evidence.

    `direction` reuses `ImpactClass` (`domain/signals`) rather than a new enum — same
    positive/negative/neutral/uncertain vocabulary the Analyst pipeline already uses for
    "likely impact", and the same cross-domain-reuse shape `domain/briefing`/`domain/
    signals` already use for `ReviewState`. `evidence` mixes evidence types (see
    `EvidenceType`): real data and historical analogs assembled deterministically from
    `ScenarioContext`/quant results, plus exactly one `[razonamiento]`-tagged item from
    the Synthesis LLM's own reasoning for this asset class — never fabricated data.
    """

    asset_class: AssetClass
    direction: ImpactClass
    confidence: float
    evidence: list[ScenarioEvidence]
