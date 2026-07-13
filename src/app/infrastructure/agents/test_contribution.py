from datetime import datetime

import pytest
from pydantic import ValidationError

from app.infrastructure.agents import Contribution, Finding, NewsSource


def test_contribution_serializes_typed_sources() -> None:
    contribution = Contribution.model_validate(
        {
            "agent": "analyst",
            "summary": "BTC has stronger evidence.",
            "findings": [
                {
                    "claim": "A dated headline supports the BTC catalyst.",
                    "source": {
                        "kind": "news",
                        "publisher": "CoinDesk",
                        "title": "Bitcoin rises after inflation data",
                        "url": "https://example.com/btc",
                        "published_at": "2026-07-15T10:00:00Z",
                    },
                },
                {
                    "claim": "BTC lost 33% in the selected window.",
                    "source": {
                        "kind": "quant",
                        "metric": "six-month normalized return",
                        "value": "-33.00%",
                        "as_of": "2026-07-15",
                    },
                },
            ],
        }
    )

    payload = contribution.model_dump(mode="json")

    assert payload["findings"][0]["source"]["kind"] == "news"
    assert payload["findings"][0]["source"]["published_at"] == "2026-07-15T10:00:00Z"
    assert payload["findings"][1]["source"]["kind"] == "quant"


def test_finding_rejects_unknown_source_kind() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(
            {
                "claim": "Unsupported",
                "source": {"kind": "memory", "value": "invented"},
            }
        )


def test_news_source_uses_datetime() -> None:
    finding = Finding.model_validate(
        {
            "claim": "Headline",
            "source": {
                "kind": "news",
                "publisher": "Reuters",
                "title": "Market update",
                "url": "https://example.com/market",
                "published_at": "2026-07-15T12:00:00Z",
            },
        }
    )

    assert isinstance(finding.source, NewsSource)
    assert isinstance(finding.source.published_at, datetime)
