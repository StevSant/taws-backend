from enum import StrEnum


class SortDirection(StrEnum):
    """Sort order for a listing query."""

    ASC = "asc"
    DESC = "desc"
