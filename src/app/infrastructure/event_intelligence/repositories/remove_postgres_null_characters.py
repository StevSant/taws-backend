from typing import Any


def remove_postgres_null_characters(value: Any) -> Any:
    """Remove NUL characters from text values before Postgres persistence.

    Postgres text columns reject U+0000. Upstream news and LLM output are both untrusted text,
    while event rows otherwise only carry scalars or flat string lists.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [item.replace("\x00", "") if isinstance(item, str) else item for item in value]
    return value
