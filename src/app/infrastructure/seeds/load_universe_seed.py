import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache
def load_universe_seed(seed_path: Path) -> list[dict[str, Any]]:
    """Load and cache the curated instrument universe as raw JSON rows.

    Rows may carry optional `coingecko_id` / `yfinance_symbol` vendor overrides —
    those stay out of the pure `Instrument` entity and are resolved by the
    infrastructure adapters that need them (see `core/di/container.py`).
    """
    with seed_path.open(encoding="utf-8") as seed_file:
        return json.load(seed_file)
