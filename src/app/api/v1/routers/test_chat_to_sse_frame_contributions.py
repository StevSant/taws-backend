"""Unit test for `_to_sse_frame(ContributionsEvent(...))` — the multi-specialist stance frame.

Asserts the exact SSE wire shape the frontend parses: `{"contributions": [{agent, stance,
confidence, headline}]}`, wrapped as a single `data: ...\n\n` frame.
"""

import json

from app.api.v1.routers.chat import _to_sse_frame
from app.domain.agents.entities import ContributionsEvent


def test_to_sse_frame_serializes_contributions_event() -> None:
    # Arrange
    event = ContributionsEvent(
        contributions=[
            {"agent": "quant", "stance": "bull", "confidence": 0.8, "headline": "Momentum up"},
            {"agent": "macro", "stance": "bear", "confidence": 0.4, "headline": "Rates weigh"},
        ]
    )

    # Act
    frame = _to_sse_frame(event)

    # Assert
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    payload = json.loads(frame[len("data: ") :].strip())
    assert payload == {
        "contributions": [
            {"agent": "quant", "stance": "bull", "confidence": 0.8, "headline": "Momentum up"},
            {"agent": "macro", "stance": "bear", "confidence": 0.4, "headline": "Rates weigh"},
        ]
    }
