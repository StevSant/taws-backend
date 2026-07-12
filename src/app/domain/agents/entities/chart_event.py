from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ChartEvent:
    """A rendered chart, as yielded by `AgentRunner.stream`. `chart` is the already-
    serialized camelCase wire dict (see `serialize_chart_spec`): it arrives that way over
    the LangGraph `custom` channel, so re-wrapping it in a domain object here would just
    force a needless round-trip. Maps 1:1 to the SSE frame `{"chart": {...}}`."""

    chart: dict[str, Any]
