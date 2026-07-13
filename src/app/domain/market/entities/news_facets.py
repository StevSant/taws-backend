from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NewsFacets:
    """Distinct filter values actually present in the persisted news store.

    Populates the browse page's source / provider dropdowns, so the UI offers only
    values that can return results instead of a hardcoded list that drifts from
    whatever the ingest pipeline is currently pulling.
    """

    sources: list[str]
    providers: list[str]
