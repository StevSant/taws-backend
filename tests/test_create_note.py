import pytest

from app.application.notes import NoteTargetNotFoundError
from app.application.notes.use_cases import CreateNote
from app.domain.notes.value_objects import NoteTarget, NoteTargetKind
from app.infrastructure.persistence import InMemoryNoteRepository

_LIVE_TARGET = NoteTarget(
    kind=NoteTargetKind.BRIEFING,
    label="Crypto weakness after CPI",
    target_id="briefing-1",
    watchlist_id="watchlist-9",
)


class _FakeResolver:
    def __init__(self, target: NoteTarget | None) -> None:
        self._target = target
        self.calls: list[tuple[NoteTargetKind, str]] = []

    async def resolve(self, kind: NoteTargetKind, target_id: str) -> NoteTarget | None:
        self.calls.append((kind, target_id))
        return self._target


async def test_creates_an_unlinked_note_without_consulting_the_resolver() -> None:
    resolver = _FakeResolver(None)
    use_case = CreateNote(InMemoryNoteRepository(), resolver)

    note = await use_case.execute(user_id="user-1", body="Plain thought")

    assert note.target is None
    assert note.user_id == "user-1"
    assert resolver.calls == []


async def test_creates_a_linked_note_with_the_server_resolved_label() -> None:
    use_case = CreateNote(InMemoryNoteRepository(), _FakeResolver(_LIVE_TARGET))

    note = await use_case.execute(
        user_id="user-1",
        body="Watch the correlation",
        target_kind=NoteTargetKind.BRIEFING,
        target_id="briefing-1",
    )

    assert note.target == _LIVE_TARGET
    assert note.target is not None
    assert note.target.available is True


async def test_creating_against_a_missing_target_raises_and_persists_nothing() -> None:
    repository = InMemoryNoteRepository()
    use_case = CreateNote(repository, _FakeResolver(None))

    with pytest.raises(NoteTargetNotFoundError):
        await use_case.execute(
            user_id="user-1",
            body="Doomed",
            target_kind=NoteTargetKind.SCENARIO,
            target_id="gone",
        )

    assert await repository.list_for_user("user-1") == []


async def test_a_kind_without_an_id_is_treated_as_unlinked() -> None:
    resolver = _FakeResolver(_LIVE_TARGET)
    use_case = CreateNote(InMemoryNoteRepository(), resolver)

    note = await use_case.execute(
        user_id="user-1", body="No id given", target_kind=NoteTargetKind.BRIEFING
    )

    assert note.target is None
    assert resolver.calls == []


async def test_each_note_gets_a_distinct_id() -> None:
    use_case = CreateNote(InMemoryNoteRepository(), _FakeResolver(None))

    first = await use_case.execute(user_id="user-1", body="One")
    second = await use_case.execute(user_id="user-1", body="Two")

    assert first.id != second.id
