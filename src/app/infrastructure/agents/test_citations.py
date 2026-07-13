import json

from app.api.v1.routers.chat import _to_sse_frame
from app.domain.agents.entities import CitationsEvent
from app.infrastructure.agents import Contribution
from app.infrastructure.agents.build_citations_from_contributions import (
    build_citations_from_contributions,
)


def test_citations_are_flattened_and_deduplicated_by_source() -> None:
    source = {
        "kind": "news",
        "publisher": "CoinDesk",
        "title": "Bitcoin rises",
        "url": "https://example.com/btc",
        "published_at": "2026-07-15T10:00:00Z",
    }
    contributions = [
        Contribution.model_validate(
            {
                "agent": "analyst",
                "summary": "News",
                "findings": [{"claim": "BTC rose after CPI.", "source": source}],
            }
        ),
        Contribution.model_validate(
            {
                "agent": "advisor",
                "summary": "Same news",
                "findings": [{"claim": "The same catalyst supports BTC.", "source": source}],
            }
        ),
    ]

    citations = build_citations_from_contributions(contributions)

    assert len(citations) == 1
    assert citations[0]["claim"] == "BTC rose after CPI."
    assert citations[0]["publisher"] == "CoinDesk"
    assert citations[0]["published_at"] == "2026-07-15T10:00:00Z"


def test_citations_event_serializes_to_its_own_sse_frame() -> None:
    citations = [
        {
            "kind": "quant",
            "claim": "BTC returned -33%.",
            "metric": "six-month return",
            "value": "-33%",
        }
    ]

    frame = _to_sse_frame(CitationsEvent(citations=citations))
    payload = json.loads(frame.removeprefix("data: "))

    assert payload == {"citations": citations}
