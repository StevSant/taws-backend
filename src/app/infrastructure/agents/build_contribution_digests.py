from typing import Any

from app.infrastructure.agents.contribution import Contribution


def build_contribution_digests(
    contributions: list[Contribution],
) -> list[dict[str, Any]]:
    """Reduce typed contributions to the per-specialist stance digest for the UI panel.

    Keeps only the presentation fields the multi-specialist `contributions` frame needs —
    `agent`, `stance`, `confidence`, `headline` — dropping the heavy `summary`/`analysis`/
    `findings` that the synthesized prose and the separate `citations` frame already carry.
    """
    return [
        {
            "agent": contribution.agent,
            "stance": contribution.stance,
            "confidence": contribution.confidence,
            "headline": contribution.headline,
        }
        for contribution in contributions
    ]
