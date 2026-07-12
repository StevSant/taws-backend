import logging
import uuid
from dataclasses import replace
from datetime import datetime

from pydantic import ValidationError

from app.application.common import build_locale_instruction
from app.application.quant.event_study_stats import EventStudyStats
from app.application.quant.market_stats import MarketStats
from app.application.scenario.format_scenario_evidence import format_scenario_evidence
from app.application.scenario.scenario_asset_class_synthesis_draft import (
    ScenarioAssetClassSynthesisDraft,
)
from app.application.scenario.scenario_context import ScenarioContext
from app.application.scenario.scenario_synthesis_extraction import ScenarioSynthesisExtraction
from app.application.scenario.scenario_synthesis_unavailable_error import (
    ScenarioSynthesisUnavailableError,
)
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.consequence.entities import ConsequenceChain
from app.domain.market.entities import AssetClass
from app.domain.market.ports import InstrumentUniverse
from app.domain.scenario.entities import (
    EvidenceType,
    ScenarioAssetClassImpact,
    ScenarioEvidence,
    ScenarioResult,
    ScenarioSpec,
)
from app.domain.signals.entities import ImpactClass

logger = logging.getLogger(__name__)

_EXTRACTION_SCHEMA_NAME = "scenario_synthesis_extraction"

# Bounds how many evidence items feed one asset class's Synthesis prompt bucket, so a
# scenario touching several noisy instruments doesn't blow up the prompt — same bounding
# rationale as `generate_briefing.py`'s `_MAX_SIGNALS_IN_CONTEXT`.
_MAX_EVIDENCE_PER_ASSET_CLASS = 8

_SYNTHESIS_SYSTEM_PROMPT = """You are the Scenario Lab Analyst — a market-intelligence agent \
that synthesizes a "what-if" market scenario into a structured impact assessment.

You are given: the scenario itself, the second-order causal chain reasoned about it, and, per \
asset class, real gathered evidence (current prices/volatility, event-study statistics, macro \
state, news, and historical analogs). Produce exactly one impact call per asset class listed \
below — direction, confidence, and one or two sentences of reasoning grounded strictly in the \
provided evidence and causal chain. Never invent facts, numbers, or events that aren't in them, \
and never claim more certainty than the evidence supports.

Also propose research/monitoring actions (e.g. "watch for...", "set an alert on...") — never \
buy/sell/order/execution instructions, and never phrased as personalized advice.

This is research/informational output only."""

# Localized, user-facing reasoning for an asset class the model did not return an impact
# call for (issue #64: never a raw internal marker — an honest, localized statement).
_UNASSESSED_REASONING: dict[str, str] = {
    "es": "No se evaluó esta clase de activo en este escenario.",
    "en": "This asset class was not assessed in this scenario.",
}

# Friendly, localized names for the macro series we surface as evidence (issue #65) — the
# cryptic series id (e.g. FEDFUNDS) is kept in parentheses for traceability rather than
# shown bare. Keyed by the macro *role*, not the configurable series id, since the id comes
# from `Settings.fred_rates_series_id`/`fred_cpi_series_id`.
_MACRO_RATE_LABEL: dict[str, str] = {
    "es": "Tasa de política monetaria",
    "en": "Policy rate",
}
_MACRO_CPI_LABEL: dict[str, str] = {
    "es": "Índice de precios al consumidor",
    "en": "Consumer price index",
}

_MONTHS: dict[str, list[str]] = {
    "es": [
        "ene", "feb", "mar", "abr", "may", "jun",
        "jul", "ago", "sep", "oct", "nov", "dic",
    ],
    "en": [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ],
}
_DEFAULT_LANG = "en"
_UNAVAILABLE: dict[str, str] = {"es": "no disponible", "en": "unavailable"}


class SynthesizeScenarioResult:
    """Scenario Lab Synthesis step (issue #12): assembles the grounded `ScenarioResult`
    from everything the earlier graph steps gathered.

    Same "LLMProvider.complete_structured for grounded synthesis" shape as
    `GenerateSignal`/`GenerateConsequenceChain` — the model never chooses or formats
    evidence itself (see `ScenarioAssetClassSynthesisDraft`'s docstring); this use case
    deterministically assembles each `ScenarioAssetClassImpact.evidence` list from the
    real `ScenarioContext`/quant results (tagged `[dato actual]`/`[análogo histórico]`)
    plus exactly one `[razonamiento]`-tagged item per asset class, built from the model's
    own `reasoning` field. Evidence detail is humanized and localized (issue #65): friendly
    macro series names, locale-formatted dates, and locale-appropriate phrasing.

    Returns an UNPERSISTED `ScenarioResult` (an `id` is assigned, but nothing is written
    yet) — the graph's separate Compliance step gates persistence, same "compliance-gate-
    then-persist" contract as `GenerateSignal`/`GenerateBriefing`, just split across two
    graph nodes instead of the tail end of one method.

    Resilience (issue #64): the structured-output call is retried up to
    `max_synthesis_attempts`, logging schema-validation failures distinctly from
    transport/provider failures. When every attempt fails it raises
    `ScenarioSynthesisUnavailableError` — it does NOT fabricate a zero-confidence
    pseudo-result with internal fallback markers. The router turns that into an honest,
    localized "analysis unavailable" error state for the UI.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        instrument_universe: InstrumentUniverse,
        max_synthesis_attempts: int,
    ) -> None:
        self._llm_provider = llm_provider
        self._instrument_universe = instrument_universe
        self._max_synthesis_attempts = max(1, max_synthesis_attempts)

    async def execute(
        self,
        spec: ScenarioSpec,
        consequence_chain: ConsequenceChain,
        context: ScenarioContext,
        quant_results: dict[str, EventStudyStats],
        locale: str,
    ) -> ScenarioResult:
        spec = _attach_empirical_likelihood(spec, quant_results)
        evidence_pool = self._build_evidence_pool(spec, context, quant_results, locale)
        extraction = await self._synthesize(spec, consequence_chain, evidence_pool, locale)

        impact_map = self._build_impact_map(spec, evidence_pool, extraction.impact_map, locale)

        return ScenarioResult(
            id=str(uuid.uuid4()),
            spec=spec,
            title=extraction.title,
            narrative=extraction.narrative,
            impact_map=impact_map,
            consequence_chain=consequence_chain,
            recommended_actions=extraction.recommended_actions,
            disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
        )

    async def _synthesize(
        self,
        spec: ScenarioSpec,
        consequence_chain: ConsequenceChain,
        evidence_pool: dict[AssetClass, list[ScenarioEvidence]],
        locale: str,
    ) -> ScenarioSynthesisExtraction:
        """Call the structured-output model with a bounded retry (issue #64).

        Distinguishes the two real failure modes and logs them distinctly instead of
        collapsing every failure into one silent fallback:
        - `ValidationError`: the model replied but its JSON didn't satisfy the schema.
        - any other exception: the provider call itself failed (no `OPENAI_API_KEY`
          configured raises `RuntimeError`; transport errors raise their own types).

        Raises `ScenarioSynthesisUnavailableError` once every attempt is exhausted, so the
        caller surfaces an honest error state rather than a fabricated result.
        """
        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content=_SYNTHESIS_SYSTEM_PROMPT + build_locale_instruction(locale),
            ),
            Message(
                role=MessageRole.USER,
                content=_build_synthesis_prompt(spec, consequence_chain, evidence_pool),
            ),
        ]
        last_error: Exception | None = None
        for attempt in range(1, self._max_synthesis_attempts + 1):
            try:
                raw = await self._llm_provider.complete_structured(
                    messages=messages,
                    schema=ScenarioSynthesisExtraction.model_json_schema(),
                    schema_name=_EXTRACTION_SCHEMA_NAME,
                )
                return ScenarioSynthesisExtraction.model_validate(raw)
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "Scenario synthesis structured output failed schema validation "
                    "(attempt %d/%d): %s",
                    attempt,
                    self._max_synthesis_attempts,
                    exc,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Scenario synthesis structured output call failed (attempt %d/%d): %s",
                    attempt,
                    self._max_synthesis_attempts,
                    exc,
                )
        logger.error(
            "Scenario synthesis unavailable for %r after %d attempt(s); surfacing an honest "
            "error state instead of a degraded pseudo-result.",
            spec.title,
            self._max_synthesis_attempts,
        )
        raise ScenarioSynthesisUnavailableError(spec.title) from last_error

    def _build_evidence_pool(
        self,
        spec: ScenarioSpec,
        context: ScenarioContext,
        quant_results: dict[str, EventStudyStats],
        locale: str,
    ) -> dict[AssetClass, list[ScenarioEvidence]]:
        """Deterministically bucket every gathered fact by the asset class it's about.

        Macro state (rates/CPI/VIX) applies broadly, so it's added to every requested
        asset class's bucket; everything else is attached only to the asset class of the
        instrument it's actually about, resolved via `InstrumentUniverse`.
        """
        pool: dict[AssetClass, list[ScenarioEvidence]] = {
            asset_class: [] for asset_class in spec.affected_asset_classes
        }

        macro_evidence = self._build_macro_evidence(context, locale)
        for evidence_list in pool.values():
            evidence_list.extend(macro_evidence)

        for symbol, stats in context.market_stats.items():
            if spec.affected_symbols and symbol == spec.affected_symbols[0]:
                target_evidence = _target_price_evidence(spec, stats, locale)
                if target_evidence is not None:
                    self._append_if_tracked(pool, symbol, target_evidence)
            self._append_if_tracked(pool, symbol, _market_stats_evidence(stats, locale))

        for symbol, event_study in quant_results.items():
            self._append_if_tracked(pool, symbol, _event_study_evidence(event_study, locale))

        for symbol, analogs in context.historical_analogs.items():
            asset_class = self._asset_class_of(symbol)
            if asset_class is None or asset_class not in pool:
                continue
            pool[asset_class].extend(analogs)

        for news_item in context.news_items:
            for symbol in news_item.related_symbols:
                self._append_if_tracked(
                    pool,
                    symbol,
                    ScenarioEvidence(
                        evidence_type=EvidenceType.ACTUAL_DATA,
                        detail=format_scenario_evidence(
                            EvidenceType.ACTUAL_DATA,
                            f"{news_item.title} ({news_item.source}, "
                            f"{_format_date(news_item.published_at, locale)})",
                        ),
                    ),
                )

        for asset_class, evidence_list in pool.items():
            pool[asset_class] = evidence_list[:_MAX_EVIDENCE_PER_ASSET_CLASS]
        return pool

    def _append_if_tracked(
        self,
        pool: dict[AssetClass, list[ScenarioEvidence]],
        symbol: str,
        evidence: ScenarioEvidence,
    ) -> None:
        asset_class = self._asset_class_of(symbol)
        if asset_class is not None and asset_class in pool:
            pool[asset_class].append(evidence)

    def _asset_class_of(self, symbol: str) -> AssetClass | None:
        instrument = self._instrument_universe.by_symbol(symbol)
        return instrument.asset_class if instrument is not None else None

    def _build_macro_evidence(
        self, context: ScenarioContext, locale: str
    ) -> list[ScenarioEvidence]:
        lang = _lang(locale)
        as_of_word = "al" if lang == "es" else "as of"
        items: list[ScenarioEvidence] = []
        if context.macro_rates is not None:
            label = _MACRO_RATE_LABEL.get(lang, _MACRO_RATE_LABEL[_DEFAULT_LANG])
            items.append(
                _actual_data_evidence(
                    f"{label} ({context.macro_rates.series_id}): "
                    f"{context.macro_rates.value:.2f}% "
                    f"({as_of_word} {_format_date(context.macro_rates.as_of, locale)})"
                )
            )
        if context.macro_cpi is not None:
            label = _MACRO_CPI_LABEL.get(lang, _MACRO_CPI_LABEL[_DEFAULT_LANG])
            items.append(
                _actual_data_evidence(
                    f"{label} ({context.macro_cpi.series_id}): "
                    f"{context.macro_cpi.value:.2f} "
                    f"({as_of_word} {_format_date(context.macro_cpi.as_of, locale)})"
                )
            )
        if context.volatility_regime is not None:
            regime = context.volatility_regime
            vix_label = (
                "Índice de volatilidad VIX" if lang == "es" else "VIX volatility index"
            )
            regime_word = "régimen" if lang == "es" else "regime"
            items.append(
                _actual_data_evidence(
                    f"{vix_label}: {regime.vix_level:.2f} "
                    f"({regime_word} {regime.regime.value}) "
                    f"({as_of_word} {_format_date(regime.as_of, locale)})"
                )
            )
        return items

    def _build_impact_map(
        self,
        spec: ScenarioSpec,
        evidence_pool: dict[AssetClass, list[ScenarioEvidence]],
        drafts: list[ScenarioAssetClassSynthesisDraft],
        locale: str,
    ) -> list[ScenarioAssetClassImpact]:
        drafts_by_class = {draft.asset_class: draft for draft in drafts}
        requested = spec.affected_asset_classes or list(drafts_by_class.keys())

        impacts: list[ScenarioAssetClassImpact] = []
        for asset_class in requested:
            draft = drafts_by_class.get(asset_class)
            reasoning = draft.reasoning if draft is not None else _unassessed_reasoning(locale)
            direction = draft.direction if draft is not None else ImpactClass.UNCERTAIN
            confidence = draft.confidence if draft is not None else 0.0
            evidence = [*evidence_pool.get(asset_class, [])]
            evidence.append(
                ScenarioEvidence(
                    evidence_type=EvidenceType.REASONING,
                    detail=format_scenario_evidence(EvidenceType.REASONING, reasoning),
                )
            )
            impacts.append(
                ScenarioAssetClassImpact(
                    asset_class=asset_class,
                    direction=direction,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
        return impacts


def _lang(locale: str) -> str:
    """Primary language subtag of `locale` (e.g. `es-MX` -> `es`), defaulting to English."""
    return locale.split("-", 1)[0].lower() if locale else _DEFAULT_LANG


def _format_date(value: datetime, locale: str) -> str:
    """Format `value` as a short, locale-appropriate date instead of raw ISO (issue #65)."""
    months = _MONTHS.get(_lang(locale), _MONTHS[_DEFAULT_LANG])
    month = months[value.month - 1]
    if _lang(locale) == "es":
        return f"{value.day} {month} {value.year}"
    return f"{month} {value.day}, {value.year}"


def _unassessed_reasoning(locale: str) -> str:
    return _UNASSESSED_REASONING.get(_lang(locale), _UNASSESSED_REASONING[_DEFAULT_LANG])


def _actual_data_evidence(text: str) -> ScenarioEvidence:
    return ScenarioEvidence(
        evidence_type=EvidenceType.ACTUAL_DATA,
        detail=format_scenario_evidence(EvidenceType.ACTUAL_DATA, text),
    )


def _market_stats_evidence(stats: MarketStats, locale: str) -> ScenarioEvidence:
    lang = _lang(locale)
    unavailable = _UNAVAILABLE.get(lang, _UNAVAILABLE[_DEFAULT_LANG])
    delta = f"{stats.price_delta_pct:+.2f}%" if stats.price_delta_pct is not None else unavailable
    volatility = (
        f"{stats.volatility_pct:.2f}% ({stats.volatility_regime.value})"
        if stats.volatility_pct is not None and stats.volatility_regime is not None
        else unavailable
    )
    if lang == "es":
        text = (
            f"{stats.instrument_symbol}: variación de precio a {stats.window_days}d {delta}, "
            f"volatilidad anualizada {volatility}"
        )
    else:
        text = (
            f"{stats.instrument_symbol} {stats.window_days}d price delta {delta}, "
            f"annualized volatility {volatility}"
        )
    return _actual_data_evidence(text)


def _event_study_evidence(stats: EventStudyStats, locale: str) -> ScenarioEvidence:
    lang = _lang(locale)
    if stats.sample_size == 0:
        if lang == "es":
            text = (
                f"{stats.instrument_symbol}: sin movimientos históricos "
                f">= {stats.move_threshold_pct:.2f}% en los últimos {stats.lookback_days}d"
            )
        else:
            text = (
                f"{stats.instrument_symbol}: no historical moves "
                f">= {stats.move_threshold_pct:.2f}% found in the last {stats.lookback_days}d"
            )
        if stats.scenario_probability_pct is not None:
            text += _probability_evidence_suffix(stats, lang)
        return _actual_data_evidence(text)
    if lang == "es":
        text = (
            f"{stats.instrument_symbol}: últimos {stats.sample_size} movimientos similares "
            f"(>= {stats.move_threshold_pct:.2f}%, ventana {stats.lookback_days}d): "
            f"mediana {stats.median_return_pct:+.2f}%, "
            f"rango {stats.min_return_pct:+.2f}% a {stats.max_return_pct:+.2f}%; "
            f"retornos posteriores medios T+1 {_format_optional_pct(stats.forward_1d_median_pct)}, "
            f"T+7 {_format_optional_pct(stats.forward_7d_median_pct)}, "
            f"T+30 {_format_optional_pct(stats.forward_30d_median_pct)}"
        )
    else:
        text = (
            f"{stats.instrument_symbol} last {stats.sample_size} similar moves "
            f"(>= {stats.move_threshold_pct:.2f}%, {stats.lookback_days}d lookback): "
            f"median {stats.median_return_pct:+.2f}%, "
            f"range {stats.min_return_pct:+.2f}% to {stats.max_return_pct:+.2f}%; "
            f"median forward returns T+1 {_format_optional_pct(stats.forward_1d_median_pct)}, "
            f"T+7 {_format_optional_pct(stats.forward_7d_median_pct)}, "
            f"T+30 {_format_optional_pct(stats.forward_30d_median_pct)}"
        )
    if stats.scenario_probability_pct is not None:
        text += _probability_evidence_suffix(stats, lang)
    return _actual_data_evidence(text)


def _build_synthesis_prompt(
    spec: ScenarioSpec,
    consequence_chain: ConsequenceChain,
    evidence_pool: dict[AssetClass, list[ScenarioEvidence]],
) -> str:
    lines = [
        f"Scenario: {spec.title}",
        f"Entity: {spec.entity}",
        f"Event type: {spec.event_type}",
        f"Magnitude: {spec.magnitude.value}",
        f"Horizon: {spec.horizon.value}",
        f"Target price: {spec.target_price if spec.target_price is not None else 'not specified'}",
        f"Direction: {spec.direction.value if spec.direction is not None else 'not specified'}",
        f"Exact timeframe days: "
        f"{spec.timeframe_days if spec.timeframe_days is not None else 'not specified'}",
        f"Description: {spec.description}",
        "",
        "Causal chain:",
        *_format_consequence_chain(consequence_chain),
        "",
        "Requested asset classes (produce exactly one impact call per class):",
        *(f"- {asset_class.value}" for asset_class in evidence_pool),
        "",
        "Gathered evidence per asset class:",
    ]
    for asset_class, evidence_list in evidence_pool.items():
        lines.append(f"- {asset_class.value}:")
        if evidence_list:
            lines.extend(f"  - {evidence.detail}" for evidence in evidence_list)
        else:
            lines.append("  - (no gathered evidence for this asset class)")
    return "\n".join(lines)


def _format_optional_pct(value: float | None) -> str:
    return f"{value:+.2f}%" if value is not None else "unavailable"


def _probability_evidence_suffix(stats: EventStudyStats, lang: str) -> str:
    probability = stats.scenario_probability_pct
    if probability is None:
        return ""
    if lang == "es":
        return (
            f"; frecuencia empírica del escenario {probability:.2f}% "
            f"({stats.scenario_probability_occurrences}/"
            f"{stats.scenario_probability_sample_size} ventanas históricas "
            f"de {stats.scenario_probability_horizon_days}d)"
        )
    return (
        f"; empirical scenario frequency {probability:.2f}% "
        f"({stats.scenario_probability_occurrences}/"
        f"{stats.scenario_probability_sample_size} historical "
        f"{stats.scenario_probability_horizon_days}d windows)"
    )


def _target_price_evidence(
    spec: ScenarioSpec,
    stats: MarketStats,
    locale: str,
) -> ScenarioEvidence | None:
    if spec.target_price is None or stats.last_price is None or stats.last_price <= 0:
        return None
    lang = _lang(locale)
    distance_pct = ((spec.target_price / stats.last_price) - 1) * 100
    if spec.timeframe_days is not None:
        timeframe = (
            f"en {spec.timeframe_days} día(s)" if lang == "es" else f"within {spec.timeframe_days} day(s)"
        )
    else:
        timeframe = (
            f"en el horizonte {spec.horizon.value}"
            if lang == "es"
            else f"over the {spec.horizon.value} horizon"
        )
    if lang == "es":
        text = (
            f"{stats.instrument_symbol} debería moverse {distance_pct:+.2f}% "
            f"desde el precio actual {stats.last_price:,.2f} "
            f"hacia el objetivo {spec.target_price:,.2f} {timeframe}"
        )
    else:
        text = (
            f"{stats.instrument_symbol} would move {distance_pct:+.2f}% from current price "
            f"{stats.last_price:,.2f} to the stated target {spec.target_price:,.2f} {timeframe}"
        )
    return _actual_data_evidence(text)


def _attach_empirical_likelihood(
    spec: ScenarioSpec,
    quant_results: dict[str, EventStudyStats],
) -> ScenarioSpec:
    if not spec.affected_symbols:
        return spec
    stats = quant_results.get(spec.affected_symbols[0])
    if stats is None or stats.scenario_probability_pct is None:
        return spec
    return replace(
        spec,
        likelihood_pct=stats.scenario_probability_pct,
        likelihood_sample_size=stats.scenario_probability_sample_size,
        likelihood_occurrences=stats.scenario_probability_occurrences,
        likelihood_method="historical_close_to_close_windows",
    )


def _format_consequence_chain(chain: ConsequenceChain) -> list[str]:
    node_labels = {node.id: node.label for node in chain.nodes}
    if not chain.edges:
        return ["(no causal chain available)"]
    return [
        f"- {node_labels.get(edge.source_node_id, edge.source_node_id)} -> "
        f"{node_labels.get(edge.target_node_id, edge.target_node_id)} "
        f"(confidence={edge.confidence:.2f}): {edge.mechanism}"
        for edge in chain.edges
    ]
