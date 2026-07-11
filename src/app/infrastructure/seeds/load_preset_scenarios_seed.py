import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache
def load_preset_scenarios_seed(seed_path: Path) -> list[dict[str, Any]]:
    """Load and cache the curated preset "what-if" scenarios as raw JSON rows.

    Consumed by the Scenario Simulation graph's Intake step (issue #12):
    `Container.get_run_scenario_simulation` passes these rows to
    `NormalizeScenarioIntake`, which maps a preset-by-id request onto a `ScenarioSpec` via
    `application/scenario/build_scenario_spec_from_preset.py`. Also exposed as raw rows
    (bilingual title/description included) via `GET /api/v1/scenarios/presets` for a
    Scenario Lab UI's preset picker.
    """
    with seed_path.open(encoding="utf-8") as seed_file:
        return json.load(seed_file)
