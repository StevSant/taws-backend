from app.domain.notes.value_objects import NoteTarget, NoteTargetKind


def test_target_with_an_id_is_available() -> None:
    target = NoteTarget(
        kind=NoteTargetKind.BRIEFING,
        label="Crypto weakness after CPI",
        target_id="briefing-1",
        watchlist_id="watchlist-1",
    )

    assert target.available is True


def test_target_whose_id_was_nulled_by_deletion_is_unavailable_but_keeps_its_label() -> None:
    """The point of the whole design: a note outlives its target and says so."""
    target = NoteTarget(kind=NoteTargetKind.BRIEFING, label="Crypto weakness after CPI")

    assert target.available is False
    assert target.label == "Crypto weakness after CPI"
    assert target.kind is NoteTargetKind.BRIEFING


def test_kind_values_match_the_database_check_constraint() -> None:
    assert [kind.value for kind in NoteTargetKind] == ["briefing", "scenario", "instrument"]
