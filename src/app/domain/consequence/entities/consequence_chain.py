from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.consequence.entities.consequence_edge import ConsequenceEdge
from app.domain.consequence.entities.consequence_node import ConsequenceNode


@dataclass(slots=True)
class ConsequenceChain:
    """A Consequence Chain Analyst-produced second-order causal chain (X -> Y -> Z, ...).

    Written by the Consequence Chain Analyst (issue #8). `nodes` + `edges` is a general
    graph shape, not a strictly linear list, so a chain can express more than one
    downstream branch (X -> Y, X -> Z) when the model reasons that way — deliberately
    reusable as-is by the future Scenario Simulation graph (issue #12), which is expected
    to call `GenerateConsequenceChain.execute(...)` directly and consume this same shape.
    No trading/execution fields exist. `disclaimer` is the same product invariant every
    other specialist output carries (never personalized advice).
    """

    id: str
    subject: str
    nodes: list[ConsequenceNode]
    edges: list[ConsequenceEdge]
    disclaimer: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
