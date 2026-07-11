from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EventStudyEvent:
    """One historical "similar event" day matched by `ComputeEventStudy`.

    `return_pct` is that day's OWN close-over-close return (the move that qualified it
    as an event), not a forward N-day outcome — see `ComputeEventStudy`'s docstring for
    why this T1 simplification was chosen and how a future forward-return event study
    would extend it.
    """

    date: datetime
    return_pct: float
