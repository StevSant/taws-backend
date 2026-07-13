"""`RefreshTrackedAnalysis` covers the whole universe, not just what someone watchlisted.

Regression cover for the "Sin señal" graveyard: this pass used to scope itself to the union of
the watchlists, so an instrument nobody had pinned was never handed to `GenerateSignal` by ANY
producer — no `signals` row, and the markets explorer (deliberately read-only, never generates
inline) rendered it "Sin señal" forever no matter how much news broke about it.

The ordering assertion is the load-bearing one: `max_symbols` truncates, so watchlisted symbols
must be taken FIRST or a big universe would starve the instruments users actually pinned.
"""

from app.application.analysis.use_cases import RefreshTrackedAnalysis
from app.domain.market.entities import AssetClass, Instrument
from app.domain.market.ports import InstrumentUniverse
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository


def _instrument(symbol: str) -> Instrument:
    return Instrument(symbol=symbol, name=symbol, asset_class=AssetClass.STOCK, currency="USD")


class _FakeUniverse(InstrumentUniverse):
    def __init__(self, symbols: list[str]) -> None:
        self._instruments = [_instrument(symbol) for symbol in symbols]

    def all(self) -> list[Instrument]:
        return list(self._instruments)

    def by_symbol(self, symbol: str) -> Instrument | None:
        return next((i for i in self._instruments if i.symbol.upper() == symbol.upper()), None)

    def by_asset_class(self, asset_class: AssetClass) -> list[Instrument]:
        return [i for i in self._instruments if i.asset_class == asset_class]


class _FakeWatchlistRepository(WatchlistRepository):
    """One watchlist holding `symbols`; only the two list_* methods are exercised."""

    def __init__(self, symbols: list[str]) -> None:
        self._symbols = symbols

    async def list_all(self):  # type: ignore[no-untyped-def]
        return [Watchlist(id="w1", user_id="u1", name="mine", position=0)]

    async def list_items(self, watchlist_id: str):  # type: ignore[no-untyped-def]
        return [
            WatchlistItem(id=f"i{n}", watchlist_id=watchlist_id, symbol=symbol)
            for n, symbol in enumerate(self._symbols)
        ]

    async def create(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def add_item(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def remove_item(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def list_for_user(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    async def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    async def rename(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def reorder(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class _RecordingGenerateSignal:
    """Stands in for `GenerateSignal`, recording every symbol it was asked to refresh."""

    def __init__(self) -> None:
        self.symbols: list[str] = []

    async def execute(self, symbol: str, locale: str) -> None:
        self.symbols.append(symbol)


class _NoopAnalyzeSentiment:
    async def execute(self, symbol: str, locale: str) -> None:
        return None


def _build(
    watchlisted: list[str],
    universe: list[str],
    *,
    cover_universe: bool = True,
    max_symbols: int = 40,
) -> tuple[RefreshTrackedAnalysis, _RecordingGenerateSignal]:
    generate_signal = _RecordingGenerateSignal()
    use_case = RefreshTrackedAnalysis(
        watchlist_repository=_FakeWatchlistRepository(watchlisted),
        generate_signal=generate_signal,  # type: ignore[arg-type]
        analyze_sentiment=_NoopAnalyzeSentiment(),  # type: ignore[arg-type]
        instrument_universe=lambda: _FakeUniverse(universe),
        locales=["es"],
        max_concurrency=4,
        cover_universe=cover_universe,
        max_symbols=max_symbols,
    )
    return use_case, generate_signal


async def test_refreshes_instruments_nobody_watchlisted() -> None:
    use_case, generate_signal = _build(watchlisted=["AAPL"], universe=["AAPL", "ETH", "JPM"])

    await use_case.execute()

    # The bug: ETH and JPM were never generated, so the explorer showed them "Sin señal".
    assert set(generate_signal.symbols) == {"AAPL", "ETH", "JPM"}


async def test_watchlisted_symbols_are_refreshed_first_so_the_cap_cannot_starve_them() -> None:
    use_case, generate_signal = _build(
        watchlisted=["TLT"],
        universe=["AAPL", "ETH", "JPM", "TLT"],
        max_symbols=2,
    )

    await use_case.execute()

    # TLT is last alphabetically — if the cap sliced a sorted universe it would be dropped.
    assert generate_signal.symbols[0] == "TLT"
    assert len(generate_signal.symbols) == 2


async def test_the_cap_bounds_the_pass() -> None:
    use_case, generate_signal = _build(
        watchlisted=[], universe=["A", "B", "C", "D", "E"], max_symbols=3
    )

    await use_case.execute()

    assert len(generate_signal.symbols) == 3


async def test_cover_universe_off_keeps_the_old_watchlist_only_scope() -> None:
    use_case, generate_signal = _build(
        watchlisted=["AAPL"], universe=["AAPL", "ETH", "JPM"], cover_universe=False
    )

    await use_case.execute()

    assert generate_signal.symbols == ["AAPL"]


async def test_a_pinned_symbol_in_the_universe_is_not_refreshed_twice() -> None:
    use_case, generate_signal = _build(watchlisted=["AAPL"], universe=["AAPL", "ETH"])

    await use_case.execute()

    assert sorted(generate_signal.symbols) == ["AAPL", "ETH"]


async def test_seeding_one_symbol_never_touches_the_universe() -> None:
    """`execute(symbols=[...])` is the watchlist-add seed — the ONE path a user request takes
    into this use case, via `Depends` on `POST /watchlists/{id}/items`. It must not read the
    universe: resolving it eagerly made that endpoint 500 whenever the universe accessor wasn't
    ready, even though the seed never consults it. Hence the accessor is injected, not the
    instance, and is only called from `_tracked_symbols`."""
    generate_signal = _RecordingGenerateSignal()

    def _exploding_universe() -> InstrumentUniverse:
        raise RuntimeError("InstrumentUniverse was not built yet")

    use_case = RefreshTrackedAnalysis(
        watchlist_repository=_FakeWatchlistRepository([]),
        generate_signal=generate_signal,  # type: ignore[arg-type]
        analyze_sentiment=_NoopAnalyzeSentiment(),  # type: ignore[arg-type]
        instrument_universe=_exploding_universe,
        locales=["es"],
        max_concurrency=4,
        cover_universe=True,
        max_symbols=40,
    )

    await use_case.execute(symbols=["AAPL"])  # must not raise

    assert generate_signal.symbols == ["AAPL"]
