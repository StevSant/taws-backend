"""Scenario domain: the Scenario Simulation graph's "what-if" market scenarios (issue #12).

A `ScenarioSpec` is the normalized intake shape both free-form text and curated presets
produce. A `ScenarioResult` is the Analyst-style synthesized output: a per-asset-class
impact map (direction + confidence + grounded evidence, each item tagged by how it's
grounded — real data, a historical analog, or reasoning) plus recommended research
actions. No trading/execution fields exist here or anywhere downstream. Own bounded
context, reusing `ConsequenceChain` (`domain/consequence`) and `ImpactClass`
(`domain/signals`) directly rather than duplicating them — the same cross-domain reuse
shape `domain/signals/ports/signal_repository.py` already uses for `ReviewState`.
"""
