from app.domain.briefing.entities import Briefing
from app.domain.market.entities import AssetClass, Instrument
from app.domain.notes.value_objects import NoteTargetKind
from app.infrastructure.notes import CompositeNoteTargetResolver


class _FakeBriefingRepository:
    async def get(self, briefing_id: str) -> Briefing | None:
        if briefing_id != "briefing-1":
            return None
        return Briefing(
            id="briefing-1",
            watchlist_id="watchlist-9",
            summary=(
                "The crypto market shows weakness after the CPI print came in hotter "
                "than expected, dragging risk assets lower across the board."
            ),
            disclaimer="not advice",
        )


class _FakeScenarioRepository:
    def __init__(self, scenario: object | None) -> None:
        self._scenario = scenario

    async def get(self, scenario_id: str) -> object | None:
        return self._scenario if scenario_id == "scenario-1" else None


class _FakeInstrumentUniverse:
    def by_symbol(self, symbol: str) -> Instrument | None:
        if symbol != "BNB":
            return None
        return Instrument(
            symbol="BNB", name="Binance Coin", asset_class=AssetClass.CRYPTO, currency="USD"
        )


def _resolver(scenario: object | None = None) -> CompositeNoteTargetResolver:
    return CompositeNoteTargetResolver(
        briefing_repository=_FakeBriefingRepository(),
        scenario_repository=_FakeScenarioRepository(scenario),
        instrument_universe=_FakeInstrumentUniverse(),
    )


async def test_briefing_label_is_the_truncated_summary_and_carries_its_watchlist() -> None:
    target = await _resolver().resolve(NoteTargetKind.BRIEFING, "briefing-1")

    assert target is not None
    assert target.available is True
    assert target.watchlist_id == "watchlist-9"
    assert target.label.startswith("The crypto market shows weakness")
    assert target.label.endswith("…")


async def test_instrument_label_is_the_instrument_name_and_has_no_watchlist() -> None:
    target = await _resolver().resolve(NoteTargetKind.INSTRUMENT, "BNB")

    assert target is not None
    assert target.label == "Binance Coin"
    assert target.target_id == "BNB"
    assert target.watchlist_id is None


async def test_unknown_target_resolves_to_none() -> None:
    assert await _resolver().resolve(NoteTargetKind.BRIEFING, "nope") is None
    assert await _resolver().resolve(NoteTargetKind.INSTRUMENT, "NOPE") is None
    assert await _resolver().resolve(NoteTargetKind.SCENARIO, "nope") is None
