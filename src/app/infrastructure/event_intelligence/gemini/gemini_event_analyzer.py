import json
import uuid
from datetime import UTC, datetime

from google import genai
from google.genai import types

from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent
from app.domain.event_intelligence.ports import EventAnalyzerPort

_ANALYSIS_SYSTEM_PROMPT = """You are a financial intelligence analyst. Your job is to analyze \
news events and determine their relevance and potential impact on financial markets.

Given a news event, produce a structured JSON analysis with the following fields:
- summary: a concise 1-2 sentence summary of the event
- importance: a float from 0.0 (irrelevant) to 1.0 (critical market-moving event)
- shouldNotify: boolean indicating whether this event warrants an alert
- affectedAssets: list of ticker symbols or asset identifiers potentially affected
- affectedSectors: list of market sectors potentially affected
- confidence: float from 0.0 to 1.0 indicating confidence in this analysis
- reasoning: brief explanation of the analysis
- suggestedQuestions: list of 1-3 follow-up questions a trader might ask

Respond ONLY with valid JSON. No markdown, no code fences, no extra text."""

_IMPACT_SYSTEM_PROMPT = """You are a financial intelligence analyst. Your job is to analyze \
how a specific market sector or asset is affected by a given news event.

Given a news event and a sector/asset, produce a concise analysis of the impact.
Consider:
- Direct exposure: how the event directly affects companies in that sector
- Indirect effects: supply chain, regulatory, or sentiment ripple effects
- Time horizon: short-term vs long-term implications
- Magnitude: mild, moderate, or severe impact

Respond with a plain text analysis (2-4 paragraphs). No markdown, no JSON, no extra formatting."""

_ANALYSIS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "importance": {"type": "number"},
        "shouldNotify": {"type": "boolean"},
        "affectedAssets": {"type": "array", "items": {"type": "string"}},
        "affectedSectors": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
        "suggestedQuestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary",
        "importance",
        "shouldNotify",
        "affectedAssets",
        "affectedSectors",
        "confidence",
        "reasoning",
        "suggestedQuestions",
    ],
}


class GeminiEventAnalyzer(EventAnalyzerPort):
    """Analyzes news events using Google Gemini, returning structured JSON.

    The model is prompted to act as a financial analyst and respond with
    a strict JSON schema — no free text, no markdown. Falls back to a
    zero-signal result when Gemini is unavailable or the API key is missing.
    """

    def __init__(self, api_key: str | None, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def analyze(self, event: NewsEvent) -> EnrichedEvent:
        if not self._api_key:
            return _fallback_enriched(event)

        client = genai.Client(api_key=self._api_key)
        prompt = _build_prompt(event)

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_ANALYSIS_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=_ANALYSIS_RESPONSE_SCHEMA,
                ),
            )
            text = response.text
            if text is None:
                return _fallback_enriched(event)
            data = json.loads(text)
        except Exception:
            return _fallback_enriched(event)

        return EnrichedEvent(
            id=str(uuid.uuid4()),
            original=event,
            summary=data.get("summary", ""),
            importance=float(data.get("importance", 0.0)),
            should_notify=bool(data.get("shouldNotify", False)),
            affected_assets=list(data.get("affectedAssets", [])),
            affected_sectors=list(data.get("affectedSectors", [])),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=data.get("reasoning", ""),
            suggested_questions=list(data.get("suggestedQuestions", [])),
            analyzed_at=datetime.now(UTC),
        )

    async def analyze_impact(self, event: EnrichedEvent, sector: str) -> str:
        if not self._api_key:
            return _fallback_impact_analysis(sector)

        client = genai.Client(api_key=self._api_key)
        prompt = _build_impact_prompt(event, sector)

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_IMPACT_SYSTEM_PROMPT,
                ),
            )
            text = response.text
            if text is None:
                return _fallback_impact_analysis(sector)
            return text.strip()
        except Exception:
            return _fallback_impact_analysis(sector)


def _build_prompt(event: NewsEvent) -> str:
    lines = [
        "Analyze the following financial news event:",
        "",
        f"Title: {event.title}",
        f"Description: {event.description}",
        f"Content: {event.content}",
        f"Source: {event.source}",
    ]
    if event.url:
        lines.append(f"URL: {event.url}")
    return "\n".join(lines)


def _build_impact_prompt(event: EnrichedEvent, sector: str) -> str:
    lines = [
        "Analyze the impact of the following news event on the specified sector/asset.",
        "",
        f"Event Title: {event.original.title}",
        f"Event Summary: {event.summary}",
        f"Event Content: {event.original.content}",
        f"Affected Sectors: {', '.join(event.affected_sectors)}",
        f"Affected Assets: {', '.join(event.affected_assets)}",
        f"Event Importance: {event.importance:.2f}",
        f"Analysis Confidence: {event.confidence:.2f}",
        f"Analysis Reasoning: {event.reasoning}",
        "",
        f"Sector/Asset to analyze: {sector}",
    ]
    return "\n".join(lines)


def _fallback_impact_analysis(sector: str) -> str:
    return (
        f"Impact analysis for {sector} is unavailable (Gemini API key not configured). "
        "Set GEMINI_API_KEY in your .env file to enable AI-powered impact analysis."
    )


def _fallback_enriched(event: NewsEvent) -> EnrichedEvent:
    return EnrichedEvent(
        id=str(uuid.uuid4()),
        original=event,
        summary="",
        importance=0.0,
        should_notify=False,
        affected_assets=[],
        affected_sectors=[],
        confidence=0.0,
        reasoning="fallback analysis (Gemini unavailable)",
        suggested_questions=[],
        analyzed_at=datetime.now(UTC),
    )
