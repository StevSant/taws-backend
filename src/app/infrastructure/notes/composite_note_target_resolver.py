from app.domain.briefing.ports import BriefingRepository
from app.domain.market.ports import InstrumentUniverse
from app.domain.notes.ports import NoteTargetResolver
from app.domain.notes.value_objects import NoteTarget, NoteTargetKind
from app.domain.scenario.ports import ScenarioRepository
from app.infrastructure.notes.truncate_label import truncate_label

# `Briefing` has no title — only a full-sentence executive summary — so a briefing's
# label is the summary's opening. Sized to stay readable in a chip.
_BRIEFING_LABEL_MAX_CHARS = 60


class CompositeNoteTargetResolver(NoteTargetResolver):
    """Resolves a note's target by asking whichever source owns that kind.

    Note the asymmetry in the three lookups, which is real and not an oversight:
    briefings and scenarios are database rows fetched via their repositories, while
    instruments live in `InstrumentUniverse` — an in-memory dict built once at boot, so
    `by_symbol` is synchronous and there is nothing to await. `InstrumentCatalogRepository`
    is deliberately not used: it exposes only `upsert`/`all_rows`, so a lookup through it
    would mean loading the whole catalog on every resolve.
    """

    def __init__(
        self,
        briefing_repository: BriefingRepository,
        scenario_repository: ScenarioRepository,
        instrument_universe: InstrumentUniverse,
    ) -> None:
        self._briefing_repository = briefing_repository
        self._scenario_repository = scenario_repository
        self._instrument_universe = instrument_universe

    async def resolve(self, kind: NoteTargetKind, target_id: str) -> NoteTarget | None:
        if kind is NoteTargetKind.BRIEFING:
            briefing = await self._briefing_repository.get(target_id)
            if briefing is None:
                return None
            return NoteTarget(
                kind=kind,
                label=truncate_label(briefing.summary, max_chars=_BRIEFING_LABEL_MAX_CHARS),
                target_id=briefing.id,
                watchlist_id=briefing.watchlist_id,
            )

        if kind is NoteTargetKind.SCENARIO:
            scenario = await self._scenario_repository.get(target_id)
            if scenario is None:
                return None
            return NoteTarget(kind=kind, label=scenario.title, target_id=scenario.id)

        instrument = self._instrument_universe.by_symbol(target_id)
        if instrument is None:
            return None
        return NoteTarget(kind=kind, label=instrument.name, target_id=instrument.symbol)
