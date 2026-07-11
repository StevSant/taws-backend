from enum import StrEnum


class ScenarioHorizon(StrEnum):
    """The time horizon over which a `ScenarioSpec`'s effects are expected to play out.

    A T1 simplification (four coarse buckets, not a precise date/duration) — good enough
    to frame the Synthesis step's prompt ("assess impact over roughly this horizon")
    without building a full time-series projection model, consistent with this codebase's
    other documented T1 simplifications (e.g. `ComputeMarketStats`'s volatility bands).
    """

    IMMEDIATE = "immediate"  # hours to ~1 day (e.g. a single headline/shock)
    SHORT_TERM = "short_term"  # about a week
    MEDIUM_TERM = "medium_term"  # about a month
    LONG_TERM = "long_term"  # a quarter or more
