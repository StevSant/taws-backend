import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache
def load_news_fixture_seed(seed_path: Path) -> list[dict[str, Any]]:
    """Load and cache the fixture news items as raw JSON rows.

    Each row carries a relative `hours_ago` instead of an absolute timestamp, so
    `FixtureNewsProvider` can convert it to "now minus hours_ago" on every call —
    fixture news always looks fresh, however long the process has been running.
    """
    with seed_path.open(encoding="utf-8") as seed_file:
        return json.load(seed_file)
