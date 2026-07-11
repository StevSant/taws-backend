import uuid

from app.application.quant.event_study_stats import EventStudyStats
from app.application.quant.market_stats import MarketStats
from app.application.scenario.format_scenario_evidence import format_scenario_evidence
from app.application.scenario.scenario_asset_class_synthesis_draft import (
    ScenarioAssetClassSynthesisDraft,
)
from app.application.scenario.scenario_context import ScenarioContext
from app.application.scenario.scenario_synthesis_extraction import ScenarioSynthesisExtraction
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

_FALLBACK_REASONING = "fallback synthesis (structured output unavailable)"
_FALLBACK_TITLE_SUFFIX = " (fallback synthesis)"


class SynthesizeScenarioResult:
    """Scenario Lab Synthesis step (issue #12): assembles the grounded `ScenarioResult`
    from everything the earlier graph steps gathered.

    Same "LLMProvider.complete_structured for grounded synthesis" shape as
    `GenerateSignal`/`GenerateConsequenceChain` — the model never chooses or formats
    evidence itself (see `ScenarioAssetClassSynthesisDraft`'s docstring); this use case
    deterministically assembles each `ScenarioAssetClassImpact.evidence` list from the
    real `ScenarioContext`/quant results (tagged `[dato actual]`/`[análogo histórico]`)
    plus exactly one `[razonamiento]`-tagged item per asset class, built from the model's
    own `reasoning` field.

    Returns an UNPERSISTED `ScenarioResult` (an `id` is assigned, but nothing is written
    yet) — the graph's separate Compliance step gates persistence, same "compliance-gate-
    then-persist" contract as `GenerateSignal`/`GenerateBriefing`, just split across two
    graph nodes instead of the tail end of one method (see the issue's explicit ask for
    distinct Synthesis/Compliance graph nodes).

    Never raises: a structured-output failure downgrades to a deterministic, zero-
    confidence "uncertain" impact call per requested asset class, same broad-catch shape
    as `GenerateConsequenceChain._extract_chain`.
    """

    def __init__(self, llm_provider: LLMProvider, instrument_universe: InstrumentUniverse) -> None:
        self._llm_provider = llm_provider
        self._instrument_universe = instrument_universe

    async def execute(
        self,
        spec: ScenarioSpec,
        consequence_chain: ConsequenceChain,
        context: ScenarioContext,
        quant_results: dict[str, EventStudyStats],
    ) -> ScenarioResult:
        evidence_pool = self._build_evidence_pool(spec, context, quant_results)
        extraction = await self._synthesize(spec, consequence_chain, evidence_pool)

        impact_map = self._build_impact_map(spec, evidence_pool, extraction.impact_map)

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
    ) -> ScenarioSynthesisExtraction:
        try:
            raw = await self._llm_provider.complete_structured(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=_SYNTHESIS_SYSTEM_PROMPT),
                    Message(
                        role=MessageRole.USER,
                        content=_build_synthesis_prompt(spec, consequence_chain, evidence_pool),
                    ),
                ],
                schema=ScenarioSynthesisExtraction.model_json_schema(),
                schema_name=_EXTRACTION_SCHEMA_NAME,
            )
            return ScenarioSynthesisExtraction.model_validate(raw)
        except Exception:
            # `OpenAIProvider.complete_structured` raises when no OPENAI_API_KEY is
            # configured; a malformed/unparseable response raises via `.model_validate`
            # above. Either way, caught here and downgraded to a fallback synthesis
            # instead of crashing the pipeline.
            return _fallback_extraction(spec, evidence_pool)

    def _build_evidence_pool(
        self,
        spec: ScenarioSpec,
        context: ScenarioContext,
        quant_results: dict[str, EventStudyStats],
    ) -> dict[AssetClass, list[ScenarioEvidence]]:
        """Deterministically bucket every gathered fact by the asset class it's about.

        Macro state (rates/CPI/VIX) applies broadly, so it's added to every requested
        asset class's bucket; everything else is attached only to the asset class of the
        instrument it's actually about, resolved via `InstrumentUniverse`.
        """
        pool: dict[AssetClass, list[ScenarioEvidence]] = {
            asset_class: [] for asset_class in spec.affected_asset_classes
        }

        macro_evidence = self._build_macro_evidence(context)
        for evidence_list in pool.values():
            evidence_list.extend(macro_evidence)

        for symbol, stats in context.market_stats.items():
            self._append_if_tracked(pool, symbol, _market_stats_evidence(stats))

        for symbol, event_study in quant_results.items():
            self._append_if_tracked(pool, symbol, _event_study_evidence(event_study))

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
                            f"{news_item.published_at.date().isoformat()})",
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

    def _build_macro_evidence(self, context: ScenarioContext) -> list[ScenarioEvidence]:
        items: list[ScenarioEvidence] = []
        if context.macro_rates is not None:
            items.append(
                _actual_data_evidence(
                    f"{context.macro_rates.series_id} (policy rate): "
                    f"{context.macro_rates.value:.2f} as of "
                    f"{context.macro_rates.as_of.date().isoformat()}"
                )
            )
        if context.macro_cpi is not None:
            items.append(
                _actual_data_evidence(
                    f"{context.macro_cpi.series_id} (CPI): {context.macro_cpi.value:.2f} as of "
                    f"{context.macro_cpi.as_of.date().isoformat()}"
                )
            )
        if context.volatility_regime is not None:
            regime = context.volatility_regime
            items.append(
                _actual_data_evidence(
                    f"VIX {regime.vix_level:.2f} ({regime.regime.value} regime) as of "
                    f"{regime.as_of.date().isoformat()}"
                )
            )
        return items

    def _build_impact_map(
        self,
        spec: ScenarioSpec,
        evidence_pool: dict[AssetClass, list[ScenarioEvidence]],
        drafts: list[ScenarioAssetClassSynthesisDraft],
    ) -> list[ScenarioAssetClassImpact]:
        drafts_by_class = {draft.asset_class: draft for draft in drafts}
        requested = spec.affected_asset_classes or list(drafts_by_class.keys())

        impacts: list[ScenarioAssetClassImpact] = []
        for asset_class in requested:
            draft = drafts_by_class.get(asset_class) or _fallback_draft(asset_class)
            evidence = [*evidence_pool.get(asset_class, [])]
            evidence.append(
                ScenarioEvidence(
                    evidence_type=EvidenceType.REASONING,
                    detail=format_scenario_evidence(EvidenceType.REASONING, draft.reasoning),
                )
            )
            impacts.append(
                ScenarioAssetClassImpact(
                    asset_class=asset_class,
                    direction=draft.direction,
                    confidence=draft.confidence,
                    evidence=evidence,
                )
            )
        return impacts


def _actual_data_evidence(text: str) -> ScenarioEvidence:
    return ScenarioEvidence(
        evidence_type=EvidenceType.ACTUAL_DATA,
        detail=format_scenario_evidence(EvidenceType.ACTUAL_DATA, text),
    )


def _market_stats_evidence(stats: MarketStats) -> ScenarioEvidence:
    delta = f"{stats.price_delta_pct:+.2f}%" if stats.price_delta_pct is not None else "unavailable"
    volatility = (
        f"{stats.volatility_pct:.2f}% ({stats.volatility_regime.value})"
        if stats.volatility_pct is not None and stats.volatility_regime is not None
        else "unavailable"
    )
    return _actual_data_evidence(
        f"{stats.instrument_symbol} {stats.window_days}d price delta {delta}, "
        f"annualized volatility {volatility}"
    )


def _event_study_evidence(stats: EventStudyStats) -> ScenarioEvidence:
    if stats.sample_size == 0:
        text = (
            f"{stats.instrument_symbol}: no historical moves >= {stats.move_threshold_pct:.2f}% "
            f"found in the last {stats.lookback_days}d"
        )
        return _actual_data_evidence(text)
    text = (
        f"{stats.instrument_symbol} last {stats.sample_size} similar moves "
        f"(>= {stats.move_threshold_pct:.2f}%, {stats.lookback_days}d lookback): "
        f"median {stats.median_return_pct:+.2f}%, "
        f"range {stats.min_return_pct:+.2f}% to {stats.max_return_pct:+.2f}%"
    )
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


def _fallback_extraction(
    spec: ScenarioSpec, evidence_pool: dict[AssetClass, list[ScenarioEvidence]]
) -> ScenarioSynthesisExtraction:
    requested = spec.affected_asset_classes or list(evidence_pool.keys())
    # `ScenarioSynthesisExtraction.impact_map` requires at least one entry; a total
    # fallback (free-form intake ALSO degraded, so no asset class was even requested) has
    # nothing real to key off, so it defaults to one degraded `stock` entry rather than
    # leaving `impact_map` empty — an arbitrary but harmless choice since `confidence=0.0`
    # and `direction=UNCERTAIN` already signal "no real data", and this only happens when
    # structured output was unavailable on both the Intake and Synthesis steps.
    fallback_map = [_fallback_draft(asset_class) for asset_class in requested]
    return ScenarioSynthesisExtraction(
        title=spec.title + _FALLBACK_TITLE_SUFFIX,
        narrative=_FALLBACK_REASONING,
        impact_map=fallback_map or [_fallback_draft(AssetClass.STOCK)],
        recommended_actions=[],
    )


def _fallback_draft(asset_class: AssetClass) -> ScenarioAssetClassSynthesisDraft:
    return ScenarioAssetClassSynthesisDraft(
        asset_class=asset_class,
        direction=ImpactClass.UNCERTAIN,
        confidence=0.0,
        reasoning=_FALLBACK_REASONING,
    )
