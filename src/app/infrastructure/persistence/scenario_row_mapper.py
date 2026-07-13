from typing import Any

from app.domain.consequence.entities import ConsequenceChain, ConsequenceEdge, ConsequenceNode
from app.domain.market.entities import AssetClass
from app.domain.scenario.entities import (
    EvidenceType,
    ScenarioAgentContribution,
    ScenarioAgentId,
    ScenarioAssetClassImpact,
    ScenarioConsensus,
    ScenarioContributionStatus,
    ScenarioDirection,
    ScenarioEvidence,
    ScenarioHorizon,
    ScenarioMagnitude,
    ScenarioResult,
    ScenarioSpec,
)
from app.domain.signals.entities import ImpactClass
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def scenario_to_row(result: ScenarioResult) -> dict[str, Any]:
    """Map a `ScenarioResult` onto the JSON-serializable shape stored in `scenarios`.

    `spec`/`impact_map`/`consequence_chain` are stored as JSONB (nested dataclasses
    don't map onto flat columns), same "JSONB for a structured nested shape" choice
    `signals.evidence` and `historical_analogs.metadata` already make. `preset_id` is
    denormalized out of `spec` into its own column purely for indexing/filtering — the
    JSONB `spec` blob remains the source of truth.
    """
    return {
        "id": result.id,
        "preset_id": result.spec.preset_id,
        "title": result.title,
        "narrative": result.narrative,
        "spec": _spec_to_row(result.spec),
        "impact_map": [_impact_to_row(impact) for impact in result.impact_map],
        "consequence_chain": _consequence_chain_to_row(result.consequence_chain),
        "recommended_actions": result.recommended_actions,
        "agent_contributions": [_contribution_to_row(item) for item in result.agent_contributions],
        "consensus": _consensus_to_row(result.consensus) if result.consensus else None,
        "disclaimer": result.disclaimer,
        "locale": result.locale,
        "created_at": result.created_at.isoformat(),
    }


def scenario_from_row(row: Any) -> ScenarioResult:
    """Map one `scenarios` table row (as returned by `supabase-py`) onto `ScenarioResult`.

    JSONB columns are already decoded into `dict`/`list` by PostgREST, so no extra JSON
    parsing is needed here. Typed `Any` rather than `dict[str, Any]` — see
    `watchlist_row_mapper.py` for why.
    """
    return ScenarioResult(
        id=row["id"],
        spec=_spec_from_row(row["spec"]),
        title=row["title"],
        narrative=row["narrative"],
        impact_map=[_impact_from_row(item) for item in row.get("impact_map") or []],
        consequence_chain=_consequence_chain_from_row(row["consequence_chain"]),
        recommended_actions=row.get("recommended_actions") or [],
        disclaimer=row["disclaimer"],
        locale=row.get("locale") or "",
        agent_contributions=[
            _contribution_from_row(item) for item in row.get("agent_contributions") or []
        ],
        consensus=_consensus_from_row(row["consensus"]) if row.get("consensus") else None,
        created_at=parse_supabase_timestamp(row["created_at"]),
    )


def _contribution_to_row(item: ScenarioAgentContribution) -> dict[str, Any]:
    return {
        "agent_id": item.agent_id.value,
        "status": item.status.value,
        "thesis": item.thesis,
        "confidence": item.confidence,
        "key_findings": item.key_findings,
        "evidence_refs": item.evidence_refs,
        "risks": item.risks,
        "recommendation": item.recommendation,
        "uncertainty": item.uncertainty,
        "failure_reason": item.failure_reason,
    }


def _contribution_from_row(data: dict[str, Any]) -> ScenarioAgentContribution:
    return ScenarioAgentContribution(
        agent_id=ScenarioAgentId(data["agent_id"]),
        status=ScenarioContributionStatus(data.get("status") or "completed"),
        thesis=data.get("thesis") or "",
        confidence=data.get("confidence") or 0.0,
        key_findings=data.get("key_findings") or [],
        evidence_refs=data.get("evidence_refs") or [],
        risks=data.get("risks") or [],
        recommendation=data.get("recommendation") or "",
        uncertainty=data.get("uncertainty") or "",
        failure_reason=data.get("failure_reason"),
    )


def _consensus_to_row(item: ScenarioConsensus) -> dict[str, Any]:
    return {
        "summary": item.summary,
        "conclusion": item.conclusion,
        "agreements": item.agreements,
        "disagreements": item.disagreements,
        "uncertainties": item.uncertainties,
        "confidence": item.confidence,
    }


def _consensus_from_row(data: dict[str, Any]) -> ScenarioConsensus:
    return ScenarioConsensus(
        summary=data.get("summary") or "",
        conclusion=data.get("conclusion") or "",
        agreements=data.get("agreements") or [],
        disagreements=data.get("disagreements") or [],
        uncertainties=data.get("uncertainties") or [],
        confidence=data.get("confidence") or 0.0,
    )


def _spec_to_row(spec: ScenarioSpec) -> dict[str, Any]:
    return {
        "entity": spec.entity,
        "event_type": spec.event_type,
        "magnitude": spec.magnitude.value,
        "horizon": spec.horizon.value,
        "title": spec.title,
        "description": spec.description,
        "target_price": spec.target_price,
        "direction": spec.direction.value if spec.direction is not None else None,
        "timeframe_days": spec.timeframe_days,
        "likelihood_pct": spec.likelihood_pct,
        "likelihood_sample_size": spec.likelihood_sample_size,
        "likelihood_occurrences": spec.likelihood_occurrences,
        "likelihood_method": spec.likelihood_method,
        "affected_symbols": spec.affected_symbols,
        "affected_asset_classes": [ac.value for ac in spec.affected_asset_classes],
        "preset_id": spec.preset_id,
    }


def _spec_from_row(data: dict[str, Any]) -> ScenarioSpec:
    return ScenarioSpec(
        entity=data["entity"],
        event_type=data["event_type"],
        magnitude=ScenarioMagnitude(data["magnitude"]),
        horizon=ScenarioHorizon(data["horizon"]),
        title=data["title"],
        description=data["description"],
        target_price=data.get("target_price"),
        direction=ScenarioDirection(data["direction"]) if data.get("direction") else None,
        timeframe_days=data.get("timeframe_days"),
        likelihood_pct=data.get("likelihood_pct"),
        likelihood_sample_size=data.get("likelihood_sample_size") or 0,
        likelihood_occurrences=data.get("likelihood_occurrences") or 0,
        likelihood_method=data.get("likelihood_method"),
        affected_symbols=data.get("affected_symbols") or [],
        affected_asset_classes=[
            AssetClass(value) for value in data.get("affected_asset_classes") or []
        ],
        preset_id=data.get("preset_id"),
    )


def _impact_to_row(impact: ScenarioAssetClassImpact) -> dict[str, Any]:
    return {
        "asset_class": impact.asset_class.value,
        "direction": impact.direction.value,
        "confidence": impact.confidence,
        "evidence": [
            {"evidence_type": item.evidence_type.value, "detail": item.detail}
            for item in impact.evidence
        ],
    }


def _impact_from_row(data: dict[str, Any]) -> ScenarioAssetClassImpact:
    return ScenarioAssetClassImpact(
        asset_class=AssetClass(data["asset_class"]),
        direction=ImpactClass(data["direction"]),
        confidence=data["confidence"],
        evidence=[
            ScenarioEvidence(
                evidence_type=EvidenceType(item["evidence_type"]), detail=item["detail"]
            )
            for item in data.get("evidence") or []
        ],
    )


def _consequence_chain_to_row(chain: ConsequenceChain) -> dict[str, Any]:
    return {
        "id": chain.id,
        "subject": chain.subject,
        "nodes": [{"id": node.id, "label": node.label} for node in chain.nodes],
        "edges": [
            {
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "mechanism": edge.mechanism,
                "confidence": edge.confidence,
            }
            for edge in chain.edges
        ],
        "disclaimer": chain.disclaimer,
        "created_at": chain.created_at.isoformat(),
    }


def _consequence_chain_from_row(data: dict[str, Any]) -> ConsequenceChain:
    return ConsequenceChain(
        id=data["id"],
        subject=data["subject"],
        nodes=[ConsequenceNode(id=n["id"], label=n["label"]) for n in data.get("nodes") or []],
        edges=[
            ConsequenceEdge(
                source_node_id=e["source_node_id"],
                target_node_id=e["target_node_id"],
                mechanism=e["mechanism"],
                confidence=e["confidence"],
            )
            for e in data.get("edges") or []
        ],
        disclaimer=data["disclaimer"],
        created_at=parse_supabase_timestamp(data["created_at"]),
    )
