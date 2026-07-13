import asyncio
import uuid

from app.application.common import build_locale_instruction
from app.application.macro.macro_asset_class_impact_draft import MacroAssetClassImpactDraft
from app.application.macro.macro_event_extraction import MacroEventExtraction
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.macro.entities import (
    ImpactMagnitude,
    MacroAssetClassImpact,
    MacroEventInterpretation,
)
from app.domain.market.entities import AssetClass, MacroObservation, VolatilityRegime
from app.domain.market.ports import MacroDataProvider
from app.domain.signals.entities import ImpactClass

_EXTRACTION_SCHEMA_NAME = "macro_event_extraction"

_DEFAULT_EVENT_DESCRIPTION = "Current macro state (no specific event described)."

_EXTRACTION_SYSTEM_PROMPT = """You are the Macro Analyst — a market-intelligence agent that \
interprets macro-economic events (interest rate decisions, CPI prints, Fed statements, and \
similar) and tags which asset classes are affected and how.

You are given the real, current macro state: the latest policy-rate reading, the latest CPI \
reading, and the VIX-derived volatility regime — plus a description of the event being \
interpreted. For every asset class listed, produce exactly one impact call: a direction \
(positive, negative, neutral, or uncertain), a magnitude (low, moderate, or high), and one or \
two sentences of rationale. Ground every call strictly in the provided rates/CPI/volatility \
figures and event description — never invent macro numbers, dates, or events that aren't given \
to you. If the event or the current state doesn't clearly point a direction for an asset class, \
prefer "uncertain" with "low" magnitude over guessing.

This is research/informational output only — never trading instructions, and never phrased as \
personalized advice."""

_FALLBACK_RATIONALE = "fallback interpretation (structured output unavailable)"


class InterpretMacroEvent:
    """Macro Analyst pipeline (issue #21): grounds a macro event description in the real
    current `MacroDataProvider` state (FRED rates/CPI + VIX-derived volatility regime,
    issue #15) and tags every tracked asset class with a direction + magnitude call.

    Deliberately NOT built on `AgentRunner` — same rationale as `GenerateConsequenceChain`/
    `AnalyzeSentiment`: a plain application-layer use case (constructor-injected with
    `MacroDataProvider` and `LLMProvider`) fits a single-call "event in, structured
    interpretation out" pipeline better than the chat/SSE-shaped `AgentRunner` contract.
    Reused as-is by the `macro` chat specialist's tool
    (`infrastructure/agents/tools/interpret_macro_event_tool.py`) and by
    `POST /api/v1/macro/interpret` (`api/v1/routers/macro.py`).

    `event_description` is optional: per the issue's architecture guidance ("or just
    fetches current MacroDataProvider state proactively"), a caller can ask "what's the
    macro picture right now" without describing a specific event — `_DEFAULT_EVENT_DESCRIPTION`
    covers that case, and the model still grounds its calls in the real rates/CPI/VIX figures.

    Tags every `AssetClass` (not just a caller-selected subset) on every call — simpler
    contract than `domain/scenario`'s `ScenarioSpec.affected_asset_classes` (which lets a
    caller narrow scope for a whole scenario simulation); this pipeline is cheap enough
    (one `complete_structured` call) that always covering the full curated asset-class
    list satisfies "tags affected asset classes for a given macro event" without an extra
    parameter to thread through the tool/REST surfaces.

    Never raises: a structured-output failure downgrades to a deterministic, zero-signal
    "uncertain"/"low magnitude" call per asset class instead of crashing the caller — same
    broad-catch shape as `GenerateConsequenceChain._extract_chain`.
    """

    def __init__(self, macro_data_provider: MacroDataProvider, llm_provider: LLMProvider) -> None:
        self._macro_data_provider = macro_data_provider
        self._llm_provider = llm_provider

    async def execute(
        self, event_description: str | None = None, locale: str | None = None
    ) -> MacroEventInterpretation:
        description = event_description or _DEFAULT_EVENT_DESCRIPTION
        rates, cpi, volatility = await asyncio.gather(
            self._macro_data_provider.get_rates(),
            self._macro_data_provider.get_cpi(),
            self._macro_data_provider.get_volatility_regime(),
        )

        extraction = await self._interpret(description, rates, cpi, volatility, locale)
        impacts = _to_impact_map(extraction.asset_class_impacts)

        return MacroEventInterpretation(
            id=str(uuid.uuid4()),
            event_description=description,
            rates=rates,
            cpi=cpi,
            volatility_regime=volatility,
            asset_class_impacts=impacts,
            disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
        )

    async def _interpret(
        self,
        event_description: str,
        rates: MacroObservation,
        cpi: MacroObservation,
        volatility: VolatilityRegime,
        locale: str | None = None,
    ) -> MacroEventExtraction:
        # `locale` is optional so a caller that doesn't care keeps the English-authored prompt
        # verbatim — same shape as `GenerateConsequenceChain._extract_chain`. When given, the
        # instruction is appended so every `rationale` comes back in the user's language: this
        # pipeline emits one or two sentences of prose per asset class, which is exactly the
        # sort of output that otherwise silently reverts to English.
        system_prompt = _EXTRACTION_SYSTEM_PROMPT
        if locale:
            system_prompt += build_locale_instruction(locale)
        try:
            raw = await self._llm_provider.complete_structured(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=system_prompt),
                    Message(
                        role=MessageRole.USER,
                        content=_format_macro_context(event_description, rates, cpi, volatility),
                    ),
                ],
                schema=MacroEventExtraction.model_json_schema(),
                schema_name=_EXTRACTION_SCHEMA_NAME,
            )
            return MacroEventExtraction.model_validate(raw)
        except Exception:
            # `OpenAIProvider.complete_structured` raises when no OPENAI_API_KEY is
            # configured; a malformed/unparseable response raises via `.model_validate`
            # above. Either way, caught here and downgraded to a fallback interpretation
            # instead of crashing the pipeline.
            return _fallback_extraction()


def _to_impact_map(
    drafts: list[MacroAssetClassImpactDraft],
) -> list[MacroAssetClassImpact]:
    """Resolve the model's drafts into one `MacroAssetClassImpact` per `AssetClass`.

    A missing asset class in the model's response (it's asked to cover every class, but
    structured-output models occasionally drop one) degrades to an explicit fallback
    entry rather than silently omitting that asset class from the result.
    """
    drafts_by_class = {draft.asset_class: draft for draft in drafts}
    return [
        _to_impact(drafts_by_class.get(asset_class) or _fallback_draft(asset_class))
        for asset_class in AssetClass
    ]


def _to_impact(draft: MacroAssetClassImpactDraft) -> MacroAssetClassImpact:
    return MacroAssetClassImpact(
        asset_class=draft.asset_class,
        direction=draft.direction,
        magnitude=draft.magnitude,
        rationale=draft.rationale,
    )


def _format_macro_context(
    event_description: str,
    rates: MacroObservation,
    cpi: MacroObservation,
    volatility: VolatilityRegime,
) -> str:
    lines = [
        f"Event: {event_description}",
        "",
        "Current macro state:",
        f"- {rates.series_id} (policy rate): {rates.value:.2f} as of "
        f"{rates.as_of.date().isoformat()}",
        f"- {cpi.series_id} (CPI): {cpi.value:.2f} as of {cpi.as_of.date().isoformat()}",
        f"- VIX {volatility.vix_level:.2f} ({volatility.regime.value} regime) as of "
        f"{volatility.as_of.date().isoformat()}",
        "",
        "Requested asset classes (produce exactly one impact call per class):",
        *(f"- {asset_class.value}" for asset_class in AssetClass),
    ]
    return "\n".join(lines)


def _fallback_extraction() -> MacroEventExtraction:
    return MacroEventExtraction(
        asset_class_impacts=[_fallback_draft(asset_class) for asset_class in AssetClass]
    )


def _fallback_draft(asset_class: AssetClass) -> MacroAssetClassImpactDraft:
    return MacroAssetClassImpactDraft(
        asset_class=asset_class,
        direction=ImpactClass.UNCERTAIN,
        magnitude=ImpactMagnitude.LOW,
        rationale=_FALLBACK_RATIONALE,
    )
