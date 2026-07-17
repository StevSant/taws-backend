import json
from typing import Any

from app.infrastructure.agents.contribution import Contribution


def build_citations_from_contributions(
    contributions: list[Contribution],
) -> list[dict[str, Any]]:
    """Flatten typed findings and keep the first claim for each unique source."""
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for contribution in contributions:
        for finding in contribution.findings:
            source = finding.source.model_dump(mode="json", exclude_none=True)
            key = (
                str(source.get("url")) if source.get("url") else json.dumps(source, sort_keys=True)
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append({"claim": finding.claim, **source})
    return citations
