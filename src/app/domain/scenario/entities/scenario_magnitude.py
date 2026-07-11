from enum import StrEnum


class ScenarioMagnitude(StrEnum):
    """How large/impactful a `ScenarioSpec`'s event is expected to be.

    Free-standing enum (not shared with `domain/market`'s `VolatilityRegime` or any other
    domain package's classification) — same "own bounded context" convention as
    `domain/signals/entities/impact_class.py`. Curated presets (`infrastructure/seeds/
    preset_scenarios.json`) set this directly per row; free-form intake has the model
    choose one via `application/scenario/scenario_spec_extraction.py`.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
