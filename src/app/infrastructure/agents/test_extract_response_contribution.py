"""Unit tests for deterministic URL validation in `extract_response_contribution`.

After the LLM extraction, any finding whose source carries a URL not present in the tool
evidence is dropped, so a fabricated link can never reach the user badged as a verified
citation. Findings whose source variant has no URL field (signal/quant/macro) are kept.
Fully offline — the model is a fake that returns a predetermined `Contribution`.
"""

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.infrastructure.agents.contribution import Contribution
from app.infrastructure.agents.extract_response_contribution import extract_response_contribution

_REAL_URL = "https://example.com/real-article"
_FAKE_URL = "https://example.com/hallucinated"


def _news_finding(claim: str, url: str) -> dict[str, Any]:
    return {
        "claim": claim,
        "source": {
            "kind": "news",
            "publisher": "Example Wire",
            "title": "Headline",
            "url": url,
            "published_at": "2026-07-15T00:00:00Z",
        },
    }


class _StructuredModel:
    def __init__(self, contribution: Contribution) -> None:
        self._contribution = contribution

    async def ainvoke(self, messages: list[Any], config: dict[str, Any]) -> Contribution:
        return self._contribution


class _ExtractionModel:
    def __init__(self, contribution: Contribution) -> None:
        self._contribution = contribution

    def with_structured_output(self, schema: type[Contribution]) -> _StructuredModel:
        assert schema is Contribution
        return _StructuredModel(self._contribution)


async def test_drops_finding_whose_url_is_absent_from_evidence() -> None:
    contribution = Contribution.model_validate(
        {
            "agent": "placeholder",
            "summary": "Two sourced claims.",
            "findings": [
                _news_finding("Real claim.", _REAL_URL),
                _news_finding("Fabricated claim.", _FAKE_URL),
            ],
        }
    )
    evidence: list[BaseMessage] = [
        ToolMessage(content=f"Article available at {_REAL_URL}", tool_call_id="call-1")
    ]

    result = await extract_response_contribution(
        _ExtractionModel(contribution),  # type: ignore[arg-type]
        "analyst",
        AIMessage(content="answer"),
        evidence_messages=evidence,
    )

    # Only the finding whose URL is grounded in the evidence survives; the agent is stamped.
    assert result.agent == "analyst"
    assert [finding.claim for finding in result.findings] == ["Real claim."]
    # The raw response prose is carried through verbatim so the synthesizer never loses it.
    assert result.analysis == "answer"


async def test_keeps_finding_whose_source_has_no_url_field() -> None:
    contribution = Contribution.model_validate(
        {
            "agent": "placeholder",
            "summary": "One computed metric.",
            "findings": [
                {
                    "claim": "BTC returned -33%.",
                    "source": {"kind": "quant", "metric": "six-month return", "value": "-33%"},
                }
            ],
        }
    )
    # Evidence with no URL at all — a URL-less source must not be dropped for lacking one.
    evidence: list[BaseMessage] = [
        ToolMessage(content="BTC six-month return computed at -33%.", tool_call_id="c1")
    ]

    result = await extract_response_contribution(
        _ExtractionModel(contribution),  # type: ignore[arg-type]
        "quant",
        AIMessage(content="answer"),
        evidence_messages=evidence,
    )

    assert [finding.claim for finding in result.findings] == ["BTC returned -33%."]


async def test_analysis_is_overwritten_with_response_content_not_the_extracted_field() -> None:
    # The structured-output call fills `analysis` with something of its own; extraction must
    # discard it and stamp the specialist's real response text so the field is never LLM-filled.
    contribution = Contribution.model_validate(
        {
            "agent": "placeholder",
            "summary": "One computed metric.",
            "analysis": "LLM-invented analysis that must be discarded.",
            "findings": [
                {
                    "claim": "BTC returned -33%.",
                    "source": {"kind": "quant", "metric": "six-month return", "value": "-33%"},
                }
            ],
        }
    )
    evidence: list[BaseMessage] = [
        ToolMessage(content="BTC six-month return computed at -33%.", tool_call_id="c1")
    ]

    result = await extract_response_contribution(
        _ExtractionModel(contribution),  # type: ignore[arg-type]
        "quant",
        AIMessage(content="The real grounded response prose."),
        evidence_messages=evidence,
    )

    assert result.analysis == "The real grounded response prose."
