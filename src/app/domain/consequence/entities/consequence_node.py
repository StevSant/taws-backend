from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConsequenceNode:
    """One state/event in a `ConsequenceChain`, e.g. "Fed raises rates 50bps".

    `id` is stable within one chain only (assigned by `GenerateConsequenceChain` as the
    chain is built, e.g. "n0", "n1", ...) so `ConsequenceEdge`s can reference nodes by id
    without depending on list order — useful once the Scenario Simulation graph (issue
    #12) starts combining chains from multiple calls into one larger causal graph.
    """

    id: str
    label: str
