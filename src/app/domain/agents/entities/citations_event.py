from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CitationsEvent:
    """Typed evidence references emitted after a grounded assistant response."""

    citations: list[dict[str, Any]]
