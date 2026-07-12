from typing import Any

from app.infrastructure.realtime.tools.args import GetNotesArgs


async def handle_get_notes(container: Any, args: Any, user_id: str) -> dict[str, Any]:
    """Return the caller's own notes, most-recently-updated first.

    Delegates to `NoteRepository.list_for_user` (issue #62), which already orders by
    `updated_at` descending. SECURITY: the list is scoped strictly by `user_id` from the
    verified JWT (threaded through `dispatch_realtime_tool`) — NEVER from the model-supplied
    arguments, so a voice call can only ever read the authenticated user's own notes. Each
    note is flattened to the fields the voice model narrates (body + timestamps).
    """
    _: GetNotesArgs = args
    repository = container.get_note_repository()
    notes = await repository.list_for_user(user_id)

    return {
        "count": len(notes),
        "notes": [
            {
                "id": note.id,
                "body": note.body,
                "updated_at": note.updated_at.isoformat(),
            }
            for note in notes
        ],
    }
