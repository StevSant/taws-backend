from app.domain.notes.entities import Note
from app.infrastructure.persistence.in_memory_note_repository import InMemoryNoteRepository


async def test_crud_is_scoped_and_sorted_by_user() -> None:
    repository = InMemoryNoteRepository()
    first = await repository.create(Note(id="n-1", user_id="user-1", body="First"))
    await repository.create(Note(id="n-2", user_id="user-2", body="Other user"))
    updated = await repository.update(first.id, "Updated")

    assert updated.body == "Updated"
    assert await repository.get(first.id) == updated
    assert [note.id for note in await repository.list_for_user("user-1")] == ["n-1"]
    assert [note.id for note in await repository.list_for_user("user-2")] == ["n-2"]

    await repository.delete(first.id)

    assert await repository.get(first.id) is None
    assert await repository.list_for_user("user-1") == []
