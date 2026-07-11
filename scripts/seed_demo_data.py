"""Demo seed script (issue #23): populates a deterministic, demo-ready dataset through the
REAL application code paths — `GenerateSignal` (issue #2), `GenerateBriefing` (issue #16),
`ScenarioSimulationRunner` (issue #12), and `ArmScenarioMonitor` (issue #18) — so the T0/T1
demo is reproducible in one command, offline or live.

Usage (single command, per the acceptance criterion):

    uv run python scripts/seed_demo_data.py

Dry-run mode — exercises the exact same pipelines against in-memory fakes instead of
Supabase, so the script's LOGIC can be verified without a reachable/configured database
(see "Known limitation" below):

    uv run python scripts/seed_demo_data.py --dry-run

What one run creates:
  - One demo watchlist ("TAWS Demo Watchlist", owned by `DEMO_USER_ID`) tracking 5
    instruments pulled from the curated universe seed
    (`src/app/infrastructure/seeds/universe.json`), one per asset class: AAPL (stock),
    BTC (crypto), TLT (credit), GLD (commodity), EURUSD (forex).
  - One Analyst `Signal` per watchlist instrument (5 signals spanning 5 asset classes),
    via `GenerateSignal`.
  - One Advisor `Briefing` for the demo watchlist, via `GenerateBriefing` — grounded in
    the signals generated above.
  - One `ScenarioResult` for the curated preset `fed-hike-50bp`, via
    `ScenarioSimulationRunner` (preset intake is a deterministic, no-LLM-call path — see
    `NormalizeScenarioIntake`'s docstring — so this step doesn't need `OPENAI_API_KEY`).
  - One armed `ScenarioMonitor` on that scenario, owned by `DEMO_USER_ID`, via
    `ArmScenarioMonitor` — the issue's explicit "at least one armed scenario" ask.

Idempotency (documented tradeoff, not an oversight): the demo watchlist is looked up by
name before creation, and its items are looked up by symbol before adding, so re-running
never duplicates the watchlist or its items. Signals / the briefing / the scenario result
are NOT deduplicated — each run appends fresh ones. This is intentional: they're
side-effect-free to repeat (no unique-key collisions), and extra signal history only makes
the briefing/historical-analog retrieval richer for a demo. The armed monitor IS
idempotent by construction (`ArmScenarioMonitor` re-arms the existing row in place rather
than creating a duplicate — see its docstring).

Known limitation (tracked separately as issue #31, not a bug in this script): live
Supabase writes need real credentials, and even with `SUPABASE_URL`/`SUPABASE_KEY` set,
the `watchlists`/`scenario_monitors` tables' RLS policies are scoped to `auth.uid()`
(see `migrations/0001_watchlists_signals_briefings.py`) — the anon `SUPABASE_KEY` alone,
with no authenticated user session, does not satisfy that policy for inserts. This
sandbox additionally has no Supabase credentials configured at all. `--dry-run` exists
specifically so this script's logic can be verified independent of that blocker; running
it for real against a live project needs either a service-role key or a real user JWT
plumbed through, which is out of scope for a demo seed script.

Why this is allowed to import `infrastructure/` directly: per `backend/CLAUDE.md`, `api/`
is the only application layer allowed to reach infrastructure, but this file is not part
of the layered application — it's a standalone ops script, the same category
`migrations/` already sits outside of.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from dataclasses import replace
from datetime import UTC, datetime

from app.application.analogs.use_cases import FindHistoricalAnalogs, IndexSignalAnalog
from app.application.briefing import EmptyWatchlistError
from app.application.briefing.use_cases import GenerateBriefing
from app.application.compliance import ComplianceViolationError
from app.application.scenario.use_cases import ArmScenarioMonitor
from app.application.signals import InsufficientEvidenceError, UnknownInstrumentError
from app.application.signals.use_cases import GenerateSignal
from app.core.config import get_settings
from app.core.di import Container, get_container
from app.domain.briefing.entities import Briefing
from app.domain.briefing.ports import BriefingRepository
from app.domain.review.entities import ReviewState
from app.domain.scenario.entities import ScenarioMonitor, ScenarioMonitorStatus, ScenarioResult
from app.domain.scenario.ports import ScenarioRepository
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository

logger = logging.getLogger("seed_demo_data")

# Fixed (not random) so re-running always addresses the same demo user/watchlist —
# deliberately not a real Supabase auth user id, see the module docstring's RLS note.
DEMO_USER_ID = "00000000-0000-0000-0000-0000000000d0"
DEMO_WATCHLIST_NAME = "TAWS Demo Watchlist"
# One symbol per asset class in the curated universe seed (stock/crypto/credit/commodity/forex).
DEMO_SYMBOLS = ["AAPL", "BTC", "TLT", "GLD", "EURUSD"]
DEMO_SCENARIO_PRESET_ID = "fed-hike-50bp"


# --- In-memory fakes, used only in --dry-run mode ------------------------------------
#
# Bundled together in one place (rather than one file per class) the same way the
# existing regression test's fakes are bundled in
# `application/briefing/use_cases/test_generate_briefing.py` — these are test-double
# support code for this script, not layered application classes.


class _InMemoryWatchlistRepository(WatchlistRepository):
    def __init__(self) -> None:
        self._watchlists: dict[str, Watchlist] = {}
        self._items: dict[str, list[WatchlistItem]] = {}

    async def create(self, watchlist: Watchlist) -> Watchlist:
        self._watchlists[watchlist.id] = watchlist
        self._items.setdefault(watchlist.id, [])
        return watchlist

    async def get(self, watchlist_id: str) -> Watchlist | None:
        return self._watchlists.get(watchlist_id)

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        return [w for w in self._watchlists.values() if w.user_id == user_id]

    async def list_all(self) -> list[Watchlist]:
        return list(self._watchlists.values())

    async def rename(self, watchlist_id: str, name: str) -> Watchlist:
        renamed = replace(self._watchlists[watchlist_id], name=name)
        self._watchlists[watchlist_id] = renamed
        return renamed

    async def delete(self, watchlist_id: str) -> None:
        self._watchlists.pop(watchlist_id, None)
        self._items.pop(watchlist_id, None)

    async def list_items(self, watchlist_id: str) -> list[WatchlistItem]:
        return list(self._items.get(watchlist_id, []))

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        item = WatchlistItem(id=str(uuid.uuid4()), watchlist_id=watchlist_id, symbol=symbol)
        self._items.setdefault(watchlist_id, []).append(item)
        return item

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        items = self._items.get(watchlist_id, [])
        self._items[watchlist_id] = [item for item in items if item.id != item_id]


class _InMemorySignalRepository(SignalRepository):
    def __init__(self) -> None:
        self._signals: dict[str, Signal] = {}
        self._review_states: dict[str, list[ReviewState]] = {}

    async def create(self, signal: Signal) -> Signal:
        self._signals[signal.id] = signal
        return signal

    async def get(self, signal_id: str) -> Signal | None:
        return self._signals.get(signal_id)

    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        return [s for s in self._signals.values() if s.instrument_symbol == symbol]

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        self._review_states.setdefault(review_state.entity_id, []).append(review_state)
        return review_state

    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        return list(self._review_states.get(signal_id, []))


class _InMemoryBriefingRepository(BriefingRepository):
    def __init__(self) -> None:
        self._briefings: dict[str, Briefing] = {}
        self._review_states: dict[str, list[ReviewState]] = {}

    async def create(self, briefing: Briefing) -> Briefing:
        self._briefings[briefing.id] = briefing
        return briefing

    async def get(self, briefing_id: str) -> Briefing | None:
        return self._briefings.get(briefing_id)

    async def list_for_watchlist(self, watchlist_id: str) -> list[Briefing]:
        return [b for b in self._briefings.values() if b.watchlist_id == watchlist_id]

    async def get_latest_for_watchlist(self, watchlist_id: str) -> Briefing | None:
        candidates = await self.list_for_watchlist(watchlist_id)
        return max(candidates, key=lambda b: b.created_at) if candidates else None

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        self._review_states.setdefault(review_state.entity_id, []).append(review_state)
        return review_state

    async def list_review_states(self, briefing_id: str) -> list[ReviewState]:
        return list(self._review_states.get(briefing_id, []))


class _InMemoryScenarioRepository(ScenarioRepository):
    def __init__(self) -> None:
        self._results: dict[str, ScenarioResult] = {}
        self._monitors: dict[str, ScenarioMonitor] = {}

    async def create(self, result: ScenarioResult) -> ScenarioResult:
        self._results[result.id] = result
        return result

    async def get(self, scenario_id: str) -> ScenarioResult | None:
        return self._results.get(scenario_id)

    async def list_recent(self, limit: int = 20) -> list[ScenarioResult]:
        ordered = sorted(self._results.values(), key=lambda r: r.created_at, reverse=True)
        return ordered[:limit]

    async def arm_monitor(self, monitor: ScenarioMonitor) -> ScenarioMonitor:
        self._monitors[monitor.id] = monitor
        return monitor

    async def get_monitor_for_user(self, scenario_id: str, user_id: str) -> ScenarioMonitor | None:
        for monitor in self._monitors.values():
            if monitor.scenario_id == scenario_id and monitor.user_id == user_id:
                return monitor
        return None

    async def list_armed_monitors(self) -> list[ScenarioMonitor]:
        return [m for m in self._monitors.values() if m.status == ScenarioMonitorStatus.ARMED]

    async def mark_monitor_matched(self, monitor_id: str, match_reason: str) -> ScenarioMonitor:
        matched = replace(
            self._monitors[monitor_id],
            status=ScenarioMonitorStatus.MATCHED,
            match_reason=match_reason,
            matched_at=datetime.now(UTC),
        )
        self._monitors[monitor_id] = matched
        return matched

    async def mark_monitor_expired(self, monitor_id: str) -> ScenarioMonitor:
        expired = replace(self._monitors[monitor_id], status=ScenarioMonitorStatus.EXPIRED)
        self._monitors[monitor_id] = expired
        return expired

    async def disarm_monitor(self, scenario_id: str, user_id: str) -> None:
        stale_ids = [
            monitor_id
            for monitor_id, monitor in self._monitors.items()
            if monitor.scenario_id == scenario_id and monitor.user_id == user_id
        ]
        for monitor_id in stale_ids:
            del self._monitors[monitor_id]


def _build_container(*, dry_run: bool) -> Container:
    """Return the `Container` to seed from.

    Real run: the process-wide cached `Container` — identical wiring to the live app.
    Dry run: a FRESH (non-cached) `Container`, with only the four persistence ports
    (Supabase-backed in the real wiring) pre-set to in-memory fakes before any `get_*`
    accessor runs — `Container`'s own lazy-caching pattern (`if self._x is None: build`)
    means pre-seeding the cache field is enough to make every downstream `get_*` call
    (including nested ones, like `get_scenario_simulation_runner`'s use of
    `get_scenario_repository`) pick up the fake instead of building a `Supabase*Repository`.
    Every other port (news, market data, LLM, embeddings, vector store) stays wired to the
    real adapters, which already degrade gracefully to fixtures/no-ops when unconfigured —
    so `--dry-run` still runs the real pipelines end to end, just without touching Supabase.
    """
    if not dry_run:
        return get_container()

    container = Container(settings=get_settings())
    container._watchlist_repository = _InMemoryWatchlistRepository()  # noqa: SLF001
    container._signal_repository = _InMemorySignalRepository()  # noqa: SLF001
    container._briefing_repository = _InMemoryBriefingRepository()  # noqa: SLF001
    container._scenario_repository = _InMemoryScenarioRepository()  # noqa: SLF001
    return container


async def _get_or_create_demo_watchlist(watchlist_repository: WatchlistRepository) -> Watchlist:
    for watchlist in await watchlist_repository.list_for_user(DEMO_USER_ID):
        if watchlist.name == DEMO_WATCHLIST_NAME:
            logger.info("Reusing existing demo watchlist %s", watchlist.id)
            return watchlist

    watchlist = Watchlist(id=str(uuid.uuid4()), user_id=DEMO_USER_ID, name=DEMO_WATCHLIST_NAME)
    created = await watchlist_repository.create(watchlist)
    logger.info("Created demo watchlist %s", created.id)
    return created


async def _ensure_watchlist_items(
    watchlist_repository: WatchlistRepository, watchlist_id: str
) -> None:
    existing_symbols = {item.symbol for item in await watchlist_repository.list_items(watchlist_id)}
    for symbol in DEMO_SYMBOLS:
        if symbol in existing_symbols:
            continue
        await watchlist_repository.add_item(watchlist_id, symbol)
        logger.info("Added %s to the demo watchlist", symbol)


async def _generate_demo_signals(container: Container) -> None:
    settings = get_settings()
    for symbol in DEMO_SYMBOLS:
        use_case = GenerateSignal(
            news_provider=container.get_news_provider(),
            market_data_provider=container.get_market_data_provider(),
            instrument_universe=container.get_instrument_universe(),
            signal_repository=container.get_signal_repository(),
            llm_provider=container.get_llm_provider(),
            find_historical_analogs=FindHistoricalAnalogs(
                embedding_provider=container.get_embedding_provider(),
                vector_store=container.get_vector_store(),
                top_k=settings.historical_analogs_top_k,
            ),
            index_signal_analog=IndexSignalAnalog(
                embedding_provider=container.get_embedding_provider(),
                vector_store=container.get_vector_store(),
            ),
        )
        try:
            signal = await use_case.execute(symbol, settings.default_locale)
        except (UnknownInstrumentError, InsufficientEvidenceError, ComplianceViolationError) as exc:
            logger.warning("Skipped signal for %s: %s", symbol, exc)
            continue
        logger.info(
            "Generated signal %s for %s (impact=%s, confidence=%.2f)",
            signal.id,
            symbol,
            signal.impact_class.value,
            signal.confidence,
        )


async def _generate_demo_briefing(container: Container, watchlist_id: str) -> None:
    use_case = GenerateBriefing(
        watchlist_repository=container.get_watchlist_repository(),
        signal_repository=container.get_signal_repository(),
        briefing_repository=container.get_briefing_repository(),
        llm_provider=container.get_llm_provider(),
    )
    try:
        briefing = await use_case.execute(watchlist_id)
    except (EmptyWatchlistError, ComplianceViolationError) as exc:
        logger.warning("Skipped briefing: %s", exc)
        return
    logger.info("Generated briefing %s for watchlist %s", briefing.id, watchlist_id)


async def _generate_and_arm_demo_scenario(container: Container) -> None:
    settings = get_settings()
    runner = container.get_scenario_simulation_runner()
    result = await runner.execute(preset_id=DEMO_SCENARIO_PRESET_ID)
    logger.info("Generated scenario %s (preset=%s)", result.id, DEMO_SCENARIO_PRESET_ID)

    arm_use_case = ArmScenarioMonitor(
        scenario_repository=container.get_scenario_repository(),
        ttl_days=settings.scenario_monitor_ttl_days,
    )
    monitor = await arm_use_case.execute(scenario_id=result.id, user_id=DEMO_USER_ID)
    if monitor is None:
        # Unreachable in practice: `result.id` was just returned by `runner.execute(...)`,
        # so the scenario the monitor looks up always exists. Guarded per this codebase's
        # "fail loudly on an unreachable state" convention (see `ScenarioSimulationRunner`).
        raise RuntimeError("Arming the demo scenario monitor unexpectedly found no scenario.")
    logger.info(
        "Armed scenario monitor %s (status=%s, expires_at=%s)",
        monitor.id,
        monitor.status.value,
        monitor.expires_at.isoformat(),
    )


async def _run(*, dry_run: bool) -> None:
    container = _build_container(dry_run=dry_run)
    watchlist_repository = container.get_watchlist_repository()

    watchlist = await _get_or_create_demo_watchlist(watchlist_repository)
    await _ensure_watchlist_items(watchlist_repository, watchlist.id)
    await _generate_demo_signals(container)
    await _generate_demo_briefing(container, watchlist.id)
    await _generate_and_arm_demo_scenario(container)

    logger.info(
        "Demo seed complete%s.", " (dry-run — nothing left this process)" if dry_run else ""
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run every pipeline against in-memory fakes instead of Supabase — no network "
        "DB writes; verifies this script's logic without live credentials.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    try:
        asyncio.run(_run(dry_run=args.dry_run))
    except RuntimeError as exc:
        # `build_supabase_client` raises `RuntimeError` when SUPABASE_URL/SUPABASE_KEY
        # aren't configured (see its docstring) — the expected failure mode for a real
        # run in an environment with no Supabase credentials. Reported plainly instead of
        # a raw traceback, with the dry-run escape hatch pointed out.
        logger.error("Seed run failed: %s", exc)
        logger.error(
            "Try `uv run python scripts/seed_demo_data.py --dry-run` to verify logic "
            "without live Supabase credentials."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
