import json
import logging
import uuid
from datetime import UTC, datetime

from google import genai
from google.genai import types

from app.application.common import build_locale_instruction
from app.domain.event_intelligence.entities import EnrichedEvent, NewsEvent
from app.domain.event_intelligence.ports import EventAnalyzerPort

logger = logging.getLogger(__name__)

_ANALYSIS_SYSTEM_PROMPT = """You are Sentinel, a senior financial intelligence analyst. Your \
job is to identify new information that warrants an immediate market alert, not to provide a \
generic sentiment label.

Assess the event's novelty, credibility, magnitude, and plausible near-term market transmission. \
Give priority to concrete catalysts: geopolitical or military escalation, central-bank or fiscal \
action, inflation/labor data surprises, sanctions or tariffs, sovereign or banking stress, major \
earnings/guidance, regulatory decisions, exchange/security failures, commodity supply shocks, and \
unusual moves in a major asset. For example, a new US-Iran military escalation accompanied by a \
material Bitcoin or oil move normally warrants an alert.

Set shouldNotify=true only when a time-sensitive investor would benefit from knowing now. Do not \
set it false merely because the directional impact is uncertain. Set shouldNotify=false for stale \
recaps, routine price commentary, unsupported opinion, minor company updates, or a duplicate with \
no meaningful new development.

Calibrate importance consistently: 0.90-1.00 = systemic/critical market event; 0.70-0.89 = \
material market-moving catalyst; 0.40-0.69 = notable but normally no immediate alert; below 0.40 \
= low relevance. A true shouldNotify result should ordinarily have importance >= 0.70.

Given a news event, produce a structured JSON analysis with these fields:
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

    **Uses the SDK's async surface (`client.aio.models`), and holds ONE client.** Both matter
    now that the scheduled Sentinel scan calls this on a timer instead of only on a manual
    button press:

    - `client.models.generate_content` is *synchronous*. Awaiting an `async def` that calls it
      does not yield — it blocks the event loop for the entire round-trip to Google. One tick
      analyzing a batch of articles would have frozen every in-flight HTTP request and the
      scheduler itself for as long as that took. `client.aio.models.generate_content` is the
      genuinely awaitable variant.
    - The client was also rebuilt on every call, discarding its connection pool each time.
    """

    def __init__(self, api_key: str | None, model: str, locale: str) -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key) if api_key else None
        # Both prompts previously ended with "write ... in the SAME LANGUAGE as the event title
        # and content". Upstream market news is overwhelmingly English, so that instruction
        # guaranteed English output — an English summary and English suggested questions, then
        # rendered inside a Spanish-framed Telegram alert ("ALERTA DE MERCADO", "Resumen").
        # Reuses the same shared locale instruction as every other LLM pipeline here, so the
        # Sentinel path can't drift to its own phrasing of the rule.
        self._locale_instruction = build_locale_instruction(locale)

    async def analyze(self, event: NewsEvent) -> EnrichedEvent:
        if self._client is None:
            logger.error(
                "Gemini is unavailable for event %s: GEMINI_API_KEY is not configured", event.title
            )
            return _fallback_enriched(event)

        prompt = _build_prompt(event)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_ANALYSIS_SYSTEM_PROMPT + self._locale_instruction,
                    response_mime_type="application/json",
                    response_schema=_ANALYSIS_RESPONSE_SCHEMA,
                ),
            )
            text = response.text
            if text is None:
                logger.error(
                    "Gemini returned no text for event %s: prompt_feedback=%s candidates=%s",
                    event.title,
                    getattr(response, "prompt_feedback", None),
                    [
                        {
                            "finish_reason": str(getattr(candidate, "finish_reason", None)),
                            "has_content": getattr(candidate, "content", None) is not None,
                        }
                        for candidate in (getattr(response, "candidates", None) or [])
                    ],
                )
                return _fallback_enriched(event)
            data = json.loads(text)
        except Exception:
            logger.exception("Gemini analysis failed for event: %s", event.title)
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
        if self._client is None:
            return _fallback_impact_analysis(sector)

        prompt = _build_impact_prompt(event, sector)

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_IMPACT_SYSTEM_PROMPT + self._locale_instruction,
                ),
            )
            text = response.text
            if text is None:
                return _fallback_impact_analysis(sector)
            return text.strip()
        except Exception:
            logger.exception("Gemini impact analysis failed for sector: %s", sector)
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
        analysis_available=False,
    )
