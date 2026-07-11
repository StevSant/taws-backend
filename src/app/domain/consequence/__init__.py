"""Consequence domain: the Consequence Chain Analyst's second-order causal chains.

A `ConsequenceChain` is a structured X -> Y -> Z causal chain (nodes + edges) reasoning
about the likely downstream effects of an event or instrument, with a mechanism
description and confidence score on every edge. Read-only research output — no
trading/execution fields, no persistence port (chains are generated on demand, not
stored). Own bounded context deliberately kept separate from `domain/signals/` (an
Analyst-produced impact call) and `domain/agents/` (the generic chat/agent runtime).
"""
