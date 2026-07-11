from dataclasses import dataclass

from app.domain.scenario.entities.evidence_type import EvidenceType


@dataclass(frozen=True, slots=True)
class ScenarioEvidence:
    """One grounding-policy-tagged citation backing a `ScenarioAssetClassImpact`.

    `detail` is a self-contained, human-readable string that already starts with the
    bracketed tag matching `evidence_type` (built via `application/scenario/
    format_scenario_evidence.py`) — e.g. `"[dato actual] BTC 30d volatility: 62.1%
    (elevated)"` — so it renders correctly even without client-side tag-to-label mapping,
    the same convention `find_historical_analogs.py`'s `_ANALOG_TAG`-prefixed
    `SignalEvidence.detail` already established. `evidence_type` is kept as its own
    structured field on top of that so a UI can filter/style by grounding type.
    """

    evidence_type: EvidenceType
    detail: str
