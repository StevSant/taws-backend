"""Shared product invariant: the exact disclaimer text attached to every `Signal` and
`Briefing` (structural fields, not just UI copy — see their entity docstrings). Pure domain
constant, no vendor imports, reused by the Analyst (`application/signals`) and Advisor
(`application/briefing`) pipelines so the wording never drifts between them.
"""

NOT_PERSONALIZED_ADVICE_DISCLAIMER = (
    "This content is informational market research, not personalized financial, investment, "
    "legal, or tax advice, and it is not a recommendation to buy, sell, or hold any instrument. "
    "Consult a licensed professional before acting on it."
)
