from typing import Any

from app.application.scenario.resolve_affected_symbols import resolve_affected_symbols
from app.domain.market.ports import InstrumentUniverse
from app.domain.scenario.entities import ScenarioHorizon, ScenarioMagnitude, ScenarioSpec


def build_scenario_spec_from_preset(
    row: dict[str, Any], instrument_universe: InstrumentUniverse
) -> ScenarioSpec:
    """Map one raw preset row (`infrastructure/seeds/preset_scenarios.json`, loaded via
    `load_preset_scenarios_seed`) onto a `ScenarioSpec` — no LLM call, no free-associating:
    a preset is already curated, fully-specified data.

    `title`/`description` use the English copy (`title_en`/`description_en`) since every
    internal pipeline prompt in this codebase is English (see `backend/CLAUDE.md`'s
    persona-scope convention); the Spanish copy (`title_es`/`description_es`) stays in the
    raw JSON row for a future localized preset picker (`GET /api/v1/scenarios/presets`
    exposes the raw rows, not this normalized `ScenarioSpec`).

    `affected_asset_classes` is deterministically re-derived from `affected_symbols` here
    (via `resolve_affected_symbols`) rather than read from the row's own
    `affected_asset_classes` field — the two are equivalent for every curated preset today,
    and deriving keeps there being exactly one source of truth instead of two that could
    drift apart.
    """
    affected_symbols, affected_asset_classes = resolve_affected_symbols(
        row.get("affected_symbols") or [], instrument_universe
    )
    return ScenarioSpec(
        entity=row["entity"],
        event_type=row["event_type"],
        magnitude=ScenarioMagnitude(row["magnitude"]),
        horizon=ScenarioHorizon(row["horizon"]),
        title=row["title_en"],
        description=row["description_en"],
        affected_symbols=affected_symbols,
        affected_asset_classes=affected_asset_classes,
        preset_id=row["id"],
    )
