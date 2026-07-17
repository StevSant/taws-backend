from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContributionsEvent:
    """The per-specialist stance digest, emitted once at synthesizer entry on a
    multi-specialist turn.

    Each item is an already-serialized `{agent, stance, confidence, headline}` dict (built by
    `build_contribution_digests`): it arrives that way over the LangGraph `custom` channel, so it
    maps 1:1 to the SSE frame `{"contributions": [...]}`. A single-specialist turn takes the direct
    specialist path, never reaches the synthesizer, and so never emits this event."""

    contributions: list[dict[str, Any]]
