from enum import StrEnum


class SupervisorRoute(StrEnum):
    """The specialist the supervisor node can hand a turn off to.

    Add a new value here (and a matching persona + node + graph edge) to add a
    specialist — see the backend `CLAUDE.md` "Add a new supervisor specialist" section.
    """

    ANALYST = "analyst"
    QUANT = "quant"
    ADVISOR = "advisor"
