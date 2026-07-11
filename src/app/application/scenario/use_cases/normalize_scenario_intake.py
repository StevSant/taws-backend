from typing import Any

from app.application.scenario.build_scenario_spec_from_preset import (
    build_scenario_spec_from_preset,
)
from app.application.scenario.invalid_scenario_intake_error import InvalidScenarioIntakeError
from app.application.scenario.resolve_affected_symbols import resolve_affected_symbols
from app.application.scenario.scenario_spec_extraction import ScenarioSpecExtraction
from app.application.scenario.unknown_preset_error import UnknownPresetError
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.market.ports import InstrumentUniverse
from app.domain.scenario.entities import ScenarioHorizon, ScenarioMagnitude, ScenarioSpec

_EXTRACTION_SCHEMA_NAME = "scenario_spec_extraction"

_INTAKE_SYSTEM_PROMPT_TEMPLATE = """You are the Scenario Lab Intake normalizer — a market- \
intelligence agent that turns a free-form "what if" market scenario description into a \
structured `ScenarioSpec`.

Given a user's free-form scenario description, normalize it: identify the core entity/sector/ \
theme, classify the kind of event, estimate its magnitude and time horizon, write a short title \
and a one-paragraph grounded restatement, and list which tracked instruments it would plausibly \
affect.

Ground everything strictly in what the user actually described — never invent extra facts, \
numbers, or events they didn't mention.

Tracked instrument universe (choose `affected_symbols` ONLY from this list, by symbol; never \
invent a symbol that isn't in it):
{universe_listing}"""

_FALLBACK_TITLE_MAX_LENGTH = 80
_FALLBACK_EVENT_TYPE = "uncertain_event"


class NormalizeScenarioIntake:
    """Scenario Lab Intake step (issue #12): free-form text or a preset id -> a normalized
    `ScenarioSpec`.

    Two intake paths, both producing the exact same `ScenarioSpec` shape so every
    downstream graph step (Context gathering, Causal chain, Quantification, Synthesis,
    Compliance) is agnostic to which one ran:

    - Preset: a deterministic, no-LLM-call lookup + mapping
      (`build_scenario_spec_from_preset`) over the curated seed rows
      (`infrastructure/seeds/preset_scenarios.json`) — already fully-specified data, so
      there's nothing to infer.
    - Free-form: an `LLMProvider.complete_structured` call (same port/pattern as
      `GenerateSignal`'s classification call and `GenerateConsequenceChain`'s extraction
      call), grounded in the real tracked-instrument-universe listing so the model can't
      invent a symbol that isn't actually trackable.

    Never raises on a bad/unavailable structured-output call (e.g. no `OPENAI_API_KEY`
    configured, or a malformed response) — downgrades to a deterministic, low-confidence-
    signaling fallback `ScenarioSpec` instead, same broad-catch-and-degrade shape as
    `GenerateConsequenceChain._extract_chain`. Only truly invalid input (neither
    `preset_id` nor `free_text` given, or an unknown `preset_id`) raises.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        instrument_universe: InstrumentUniverse,
        preset_rows: list[dict[str, Any]],
    ) -> None:
        self._llm_provider = llm_provider
        self._instrument_universe = instrument_universe
        self._preset_rows = preset_rows

    async def execute(
        self, *, preset_id: str | None = None, free_text: str | None = None
    ) -> ScenarioSpec:
        if preset_id:
            return self._from_preset(preset_id)
        if free_text and free_text.strip():
            return await self._from_free_text(free_text.strip())
        raise InvalidScenarioIntakeError

    def _from_preset(self, preset_id: str) -> ScenarioSpec:
        for row in self._preset_rows:
            if row.get("id") == preset_id:
                return build_scenario_spec_from_preset(row, self._instrument_universe)
        raise UnknownPresetError(preset_id)

    async def _from_free_text(self, free_text: str) -> ScenarioSpec:
        try:
            raw = await self._llm_provider.complete_structured(
                messages=[
                    Message(
                        role=MessageRole.SYSTEM,
                        content=_INTAKE_SYSTEM_PROMPT_TEMPLATE.format(
                            universe_listing=self._format_universe_listing()
                        ),
                    ),
                    Message(role=MessageRole.USER, content=free_text),
                ],
                schema=ScenarioSpecExtraction.model_json_schema(),
                schema_name=_EXTRACTION_SCHEMA_NAME,
            )
            extraction = ScenarioSpecExtraction.model_validate(raw)
        except Exception:
            # `OpenAIProvider.complete_structured` raises when no OPENAI_API_KEY is
            # configured; a malformed/unparseable response raises via `.model_validate`
            # above. Either way, caught here and downgraded to a fallback spec instead of
            # crashing the pipeline — same broad-catch shape as `generate_signal.py`'s
            # `_classify_impact` guard.
            return _fallback_spec(free_text)

        affected_symbols, affected_asset_classes = resolve_affected_symbols(
            extraction.affected_symbols, self._instrument_universe
        )
        return ScenarioSpec(
            entity=extraction.entity,
            event_type=extraction.event_type,
            magnitude=extraction.magnitude,
            horizon=extraction.horizon,
            title=extraction.title,
            description=extraction.description,
            affected_symbols=affected_symbols,
            affected_asset_classes=affected_asset_classes,
            preset_id=None,
        )

    def _format_universe_listing(self) -> str:
        return "\n".join(
            f"- {instrument.symbol} ({instrument.name}, {instrument.asset_class.value})"
            for instrument in self._instrument_universe.all()
        )


def _fallback_spec(free_text: str) -> ScenarioSpec:
    title = (
        free_text
        if len(free_text) <= _FALLBACK_TITLE_MAX_LENGTH
        else (free_text[: _FALLBACK_TITLE_MAX_LENGTH - 1] + "…")
    )
    return ScenarioSpec(
        entity=free_text,
        event_type=_FALLBACK_EVENT_TYPE,
        magnitude=ScenarioMagnitude.MEDIUM,
        horizon=ScenarioHorizon.MEDIUM_TERM,
        title=title,
        description=free_text,
        affected_symbols=[],
        affected_asset_classes=[],
        preset_id=None,
    )
