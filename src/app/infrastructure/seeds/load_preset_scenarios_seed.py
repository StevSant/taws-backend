import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache
def load_preset_scenarios_seed(seed_path: Path) -> list[dict[str, Any]]:
    """Load and cache the curated preset "what-if" scenarios as raw JSON rows.

    Data only for now — no domain entity or scenario engine consumes this yet;
    it exists so the Scenario Lab feature has curated presets ready to build on.
    """
    with seed_path.open(encoding="utf-8") as seed_file:
        return json.load(seed_file)
