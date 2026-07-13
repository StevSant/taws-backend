from enum import StrEnum


class SupervisorRoute(StrEnum):
    """The route the supervisor node can hand a turn off to.

    The first six are market specialists. `SMALLTALK` and `OUT_OF_SCOPE` are the scope
    gate: greetings/meta questions and off-topic requests are classified here by the
    supervisor so they never reach a market specialist that could be talked into
    answering them (or into fabricating a market angle for them).

    Add a new value here (and a matching persona + node + graph edge) to add a
    specialist — see the backend `CLAUDE.md` "Add a new supervisor specialist" section.
    """

    ANALYST = "analyst"
    QUANT = "quant"
    ADVISOR = "advisor"
    CONSEQUENCE = "consequence"
    MACRO = "macro"
    SENTIMENT = "sentiment"
    SMALLTALK = "smalltalk"
    OUT_OF_SCOPE = "out_of_scope"
