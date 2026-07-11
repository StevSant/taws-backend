from pydantic import BaseModel


class ScenarioPresetResponse(BaseModel):
    """Response payload for one curated preset scenario (`GET /api/v1/scenarios/presets`).

    Maps the raw seed row directly (`infrastructure/seeds/preset_scenarios.json`), bilingual
    fields included, so a Scenario Lab preset picker doesn't need to hardcode the preset list
    (see `backend/CLAUDE.md`'s "no hardcoded values" rule) or re-implement localization —
    intentionally NOT the normalized `ScenarioSpecResponse` shape, which is English-only and
    internal-pipeline-oriented (see `build_scenario_spec_from_preset.py`).
    """

    id: str
    title_es: str
    title_en: str
    description_es: str
    description_en: str
    entity: str
    event_type: str
    magnitude: str
    horizon: str
    affected_symbols: list[str]
    affected_asset_classes: list[str]
