from enum import StrEnum


class ScenarioDirection(StrEnum):
    """Direction of the primary numeric shock described by the user."""

    UP = "up"
    DOWN = "down"
    UNCHANGED = "unchanged"
