from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChartAxis:
    """Axis metadata. `type` is one of "time"/"category"/"value"; `format` is an optional
    display hint ("currency"/"percent"/"number") the frontend uses for tick labels."""

    label: str
    type: str
    format: str | None = None
