from app.domain.notes.value_objects import NoteTarget, NoteTargetKind
from app.infrastructure.persistence.note_row_mapper import note_from_row, note_target_columns

_BASE_ROW = {
    "id": "note-1",
    "user_id": "user-1",
    "body": "Watch the BTC/NASDAQ correlation.",
    "created_at": "2026-07-17T00:00:00+00:00",
    "updated_at": "2026-07-17T00:00:00+00:00",
}


def test_row_without_a_kind_maps_to_an_unlinked_note() -> None:
    note = note_from_row({**_BASE_ROW, "target_kind": None})

    assert note.target is None


def test_row_with_a_live_briefing_maps_to_an_available_target() -> None:
    note = note_from_row(
        {
            **_BASE_ROW,
            "target_kind": "briefing",
            "briefing_id": "briefing-1",
            "target_watchlist_id": "watchlist-9",
            "target_label": "Crypto weakness after CPI",
        }
    )

    assert note.target is not None
    assert note.target.kind is NoteTargetKind.BRIEFING
    assert note.target.target_id == "briefing-1"
    assert note.target.watchlist_id == "watchlist-9"
    assert note.target.available is True


def test_row_whose_briefing_was_deleted_keeps_its_label_and_reports_unavailable() -> None:
    """THE test. `on delete set null` nulls the FK; kind and label are the durable pair.

    This is the case that silently destroys user data if we get it wrong, and it is the
    part of the cascade that lives in OUR code — Postgres owns the nulling itself, which
    Task 13 verifies by hand against a real database.
    """
    note = note_from_row(
        {
            **_BASE_ROW,
            "target_kind": "briefing",
            "briefing_id": None,
            "target_watchlist_id": None,
            "target_label": "Crypto weakness after CPI",
        }
    )

    assert note.target is not None
    assert note.target.available is False
    assert note.target.label == "Crypto weakness after CPI"
    assert note.target.kind is NoteTargetKind.BRIEFING
    assert note.body == "Watch the BTC/NASDAQ correlation."


def test_instrument_target_reads_the_symbol_column() -> None:
    note = note_from_row(
        {
            **_BASE_ROW,
            "target_kind": "instrument",
            "instrument_symbol": "BNB",
            "target_label": "Binance Coin",
        }
    )

    assert note.target is not None
    assert note.target.target_id == "BNB"
    assert note.target.available is True


def test_columns_for_no_target_are_all_null() -> None:
    assert note_target_columns(None) == {
        "target_kind": None,
        "briefing_id": None,
        "scenario_id": None,
        "instrument_symbol": None,
        "target_watchlist_id": None,
        "target_label": None,
    }


def test_columns_for_a_briefing_target_fill_only_the_briefing_arc() -> None:
    columns = note_target_columns(
        NoteTarget(
            kind=NoteTargetKind.BRIEFING,
            label="Crypto weakness after CPI",
            target_id="briefing-1",
            watchlist_id="watchlist-9",
        )
    )

    assert columns == {
        "target_kind": "briefing",
        "briefing_id": "briefing-1",
        "scenario_id": None,
        "instrument_symbol": None,
        "target_watchlist_id": "watchlist-9",
        "target_label": "Crypto weakness after CPI",
    }


def test_columns_for_a_scenario_target_fill_only_the_scenario_arc() -> None:
    columns = note_target_columns(
        NoteTarget(kind=NoteTargetKind.SCENARIO, label="Oil shock", target_id="scenario-1")
    )

    assert columns["scenario_id"] == "scenario-1"
    assert columns["briefing_id"] is None
    assert columns["instrument_symbol"] is None
    assert columns["target_watchlist_id"] is None
