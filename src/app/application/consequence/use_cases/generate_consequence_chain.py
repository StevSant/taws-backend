import uuid

from app.application.consequence.consequence_chain_extraction import ConsequenceChainExtraction
from app.application.consequence.consequence_edge_draft import ConsequenceEdgeDraft
from app.application.consequence.consequence_node_draft import ConsequenceNodeDraft
from app.domain.agents.entities import Message, MessageRole
from app.domain.agents.ports import LLMProvider
from app.domain.compliance import NOT_PERSONALIZED_ADVICE_DISCLAIMER
from app.domain.consequence.entities import ConsequenceChain, ConsequenceEdge, ConsequenceNode

_EXTRACTION_SCHEMA_NAME = "consequence_chain_extraction"

_EXTRACTION_SYSTEM_PROMPT = """You are the Consequence Chain Analyst — a market-intelligence \
agent that performs second-order reasoning about a financial event or instrument.

Given a subject (an event, headline, or instrument), produce a causal chain of 3-5 nodes \
tracing its likely downstream effects: X -> Y -> Z, and further if the reasoning holds. Every \
edge between two nodes must carry its own mechanism (one or two sentences explaining *why* the \
source plausibly leads to the target) and its own confidence score between 0 and 1 — later hops \
in a chain are typically less certain than earlier ones, and that should show up as lower \
confidence, not be hidden.

Ground every node and mechanism in general, defensible causal/economic reasoning. Never invent \
specific facts, dates, or figures you cannot support. If a plausible chain has fewer than three \
confident hops, keep it shorter rather than padding it with speculation.

This is research/informational output only — never trading instructions, and never phrased as \
personalized advice."""

_FALLBACK_MECHANISM = "fallback chain (structured output unavailable)"


class GenerateConsequenceChain:
    """Consequence Chain Analyst: turns an event/instrument description into a structured
    second-order causal chain (X -> Y -> Z) with a per-edge mechanism + confidence.

    A plain application-layer use case (constructor-injected with only `LLMProvider`), not
    built on `AgentRunner` — same rationale as `application/signals/use_cases/
    generate_signal.py`: `AgentRunner.stream(thread_id, message)` is shaped for SSE chat
    turns, not a single-call "subject in, structured entity out" pipeline. Kept deliberately
    dependency-light (no repository — chains are generated on demand, never persisted) so it
    stays trivially reusable:
    - as a chat tool for the `consequence` Supervisor specialist (see
      `infrastructure/agents/tools/generate_consequence_chain_tool.py`), and
    - directly by `POST /api/v1/consequence-chains/generate`
      (`api/v1/routers/consequence_chains.py`), and
    - by the future Scenario Simulation graph's "Causal chain" step (issue #12) — that
      graph is being built in parallel by a different worktree; it only needs to call
      `execute(subject)` and consume the returned `ConsequenceChain`, no other coupling.

    Uses `LLMProvider.complete_structured(...)` (not a LangChain `BaseChatModel` directly),
    per `backend/CLAUDE.md`'s hexagonal rule that `application/` never imports a vendor/
    framework package directly — the exact same port `generate_signal.py` uses, reused
    as-is rather than adding a parallel structured-output mechanism.

    Never raises: a structured-output failure (e.g. no `OPENAI_API_KEY` configured, or a
    malformed response) is caught and downgraded to a two-node, zero-confidence fallback
    chain instead of crashing the caller — same broad-catch shape as `generate_signal.py`'s
    `_classify_impact` guard, so both the chat tool-calling loop and the REST endpoint keep
    working without a key.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm_provider = llm_provider

    async def execute(self, subject: str) -> ConsequenceChain:
        extraction = await self._extract_chain(subject)
        return _to_chain(subject, extraction)

    async def _extract_chain(self, subject: str) -> ConsequenceChainExtraction:
        try:
            raw = await self._llm_provider.complete_structured(
                messages=[
                    Message(role=MessageRole.SYSTEM, content=_EXTRACTION_SYSTEM_PROMPT),
                    Message(role=MessageRole.USER, content=f"Subject: {subject}"),
                ],
                schema=ConsequenceChainExtraction.model_json_schema(),
                schema_name=_EXTRACTION_SCHEMA_NAME,
            )
            return ConsequenceChainExtraction.model_validate(raw)
        except Exception:
            # `OpenAIProvider.complete_structured` raises when no OPENAI_API_KEY is
            # configured (see its docstring); a malformed/unparseable response raises via
            # `.model_validate(raw)` above. Either way, caught here and downgraded to an
            # explicit "unavailable" 2-node/1-edge chain instead of crashing the pipeline.
            return _fallback_extraction()


def _to_chain(subject: str, extraction: ConsequenceChainExtraction) -> ConsequenceChain:
    """Resolve the model's positional `ConsequenceChainExtraction` into a real `ConsequenceChain`.

    Assigns stable `n<index>` ids to nodes and resolves each edge's `source_index`/
    `target_index` against them, clamping out-of-range indices into bounds instead of
    raising — a model response that's well-formed JSON but references a bad index must
    still degrade gracefully, not crash the caller.
    """
    nodes = [
        ConsequenceNode(id=f"n{index}", label=draft.label)
        for index, draft in enumerate(extraction.nodes)
    ]
    node_ids = [node.id for node in nodes]
    edges = [_to_edge(edge_draft, node_ids) for edge_draft in extraction.edges]
    return ConsequenceChain(
        id=str(uuid.uuid4()),
        subject=subject,
        nodes=nodes,
        edges=edges,
        disclaimer=NOT_PERSONALIZED_ADVICE_DISCLAIMER,
    )


def _to_edge(draft: ConsequenceEdgeDraft, node_ids: list[str]) -> ConsequenceEdge:
    return ConsequenceEdge(
        source_node_id=_node_id_at(node_ids, draft.source_index),
        target_node_id=_node_id_at(node_ids, draft.target_index),
        mechanism=draft.mechanism,
        confidence=draft.confidence,
    )


def _node_id_at(node_ids: list[str], index: int) -> str:
    """Clamp `index` into `node_ids`' bounds so an out-of-range model index never crashes."""
    bounded_index = min(max(index, 0), len(node_ids) - 1)
    return node_ids[bounded_index]


def _fallback_extraction() -> ConsequenceChainExtraction:
    return ConsequenceChainExtraction(
        nodes=[
            ConsequenceNodeDraft(label="Subject"),
            ConsequenceNodeDraft(label="Effect unknown"),
        ],
        edges=[
            ConsequenceEdgeDraft(
                source_index=0,
                target_index=1,
                mechanism=_FALLBACK_MECHANISM,
                confidence=0.0,
            )
        ],
    )
