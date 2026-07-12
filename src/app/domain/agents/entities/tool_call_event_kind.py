from enum import StrEnum


class ToolCallEventKind(StrEnum):
    START = "start"
    DONE = "done"
