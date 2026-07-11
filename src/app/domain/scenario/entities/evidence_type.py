from enum import StrEnum


class EvidenceType(StrEnum):
    """The grounding-policy tag on one `ScenarioEvidence` item (issue #12).

    Every claim in a `ScenarioResult` must be labeled by how it's grounded — this is the
    product's explicit "no free-associating" invariant for the Scenario Lab, same spirit
    as `NOT_PERSONALIZED_ADVICE_DISCLAIMER` is for trading language. The display label for
    each value is the literal bracketed tag from the issue's grounding policy (see
    `application/scenario/format_scenario_evidence.py`), not the enum's own string value:

    - `ACTUAL_DATA` -> "[dato actual]": a real, computed/fetched number (price delta,
      volatility, event-study stats, macro observation, a news item).
    - `HISTORICAL_ANALOG` -> "[análogo histórico]": a retrieved past event from
      `FindHistoricalAnalogs` (issue #15).
    - `REASONING` -> "[razonamiento]": the Synthesis LLM's own interpretive reasoning,
      never presented as if it were a fact.
    """

    ACTUAL_DATA = "actual_data"
    HISTORICAL_ANALOG = "historical_analog"
    REASONING = "reasoning"
