from enum import StrEnum


class InstrumentSortField(StrEnum):
    """Sortable columns for the enriched instruments listing (markets explorer)."""

    PRICE = "price"
    CHANGE = "change"
    NAME = "name"
