from dataclasses import dataclass, field

from app.domain.market.entities import AssetClass
from app.domain.scenario.entities.scenario_direction import ScenarioDirection
from app.domain.scenario.entities.scenario_horizon import ScenarioHorizon
from app.domain.scenario.entities.scenario_magnitude import ScenarioMagnitude


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """The normalized shape both free-form and preset Scenario Lab intake produce.

    `entity`/`event_type`/`magnitude`/`horizon` are the four fields the issue's
    architecture guidance calls out explicitly. The remaining fields are the practical
    minimum the rest of the graph needs to actually run from a `ScenarioSpec` alone,
    without re-deriving them at every downstream node:

    - `title`/`description`: a human-readable label and a normalized one-paragraph
      restatement, used as the Causal chain step's `subject` and as grounding context for
      the Synthesis step's prompt — never re-derived from `entity`/`event_type` by a
      downstream node, so there's exactly one place text normalization happens.
    - `affected_symbols`: the instrument symbols this scenario plausibly touches,
      resolved against `InstrumentUniverse` and capped at intake time (see
      `application/scenario/resolve_affected_symbols.py`) — explicit for presets, model-
      inferred (then validated) for free-form. Drives which instruments the Context
      gathering and Quantification steps fetch data for.
    - `affected_asset_classes`: derived deterministically from `affected_symbols` (never
      independently chosen by a model), so it can't drift out of sync with the symbol
      list — see `resolve_affected_symbols.py`. Drives the Synthesis step's per-asset-
      class impact map.
    - `preset_id`: the originating preset's id, or `None` for free-form intake.
    """

    entity: str
    event_type: str
    magnitude: ScenarioMagnitude
    horizon: ScenarioHorizon
    title: str
    description: str
    target_price: float | None = None
    direction: ScenarioDirection | None = None
    timeframe_days: int | None = None
    likelihood_pct: float | None = None
    likelihood_sample_size: int = 0
    likelihood_occurrences: int = 0
    likelihood_method: str | None = None
    affected_symbols: list[str] = field(default_factory=list)
    affected_asset_classes: list[AssetClass] = field(default_factory=list)
    preset_id: str | None = None
