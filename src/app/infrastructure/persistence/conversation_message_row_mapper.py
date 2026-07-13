from typing import Any

from app.domain.agents.entities import Message, MessageRole


def conversation_message_from_row(row: Any) -> Message:
    """Map one `conversation_messages` table row onto the domain `Message`.

    `ordinal` is deliberately dropped: it exists to give the rows a stable order in the
    database, but `Message` is a pure domain entity whose position is implied by its index
    in `Conversation.messages`. The repository is what applies the ordering (`order("ordinal")`).

    `charts` is read defensively with `.get`: the column is nullable and only written for
    chart-bearing assistant turns, and a database that predates the migration won't return it
    at all — either way the turn maps to a `Message` with no charts rather than raising.
    """
    charts = row.get("charts") if hasattr(row, "get") else None
    citations = row.get("citations") if hasattr(row, "get") else None
    return Message(
        role=MessageRole(row["role"]),
        content=row["content"],
        charts=list(charts) if charts else [],
        citations=list(citations) if citations else [],
    )
