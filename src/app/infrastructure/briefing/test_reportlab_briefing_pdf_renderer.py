"""Regression test for the unescaped-`symbol` PDF export crash (issue #22 follow-up).

Every user/LLM-composed field this renderer draws from `Briefing` is escaped via
`_escape()` before being handed to reportlab's `Paragraph`, which parses its input as
a small XML-like markup language — except `symbol` was missed. A watchlist item's
`symbol` (`WatchlistItemAddRequest.symbol`, length-validated only, no charset
restriction, just `.upper()`'d) flows unescaped into
`_build_instrument_section`'s `Paragraph(section.symbol, ...)`, so a symbol like
`"AAPL</b>"` throws an unhandled `ValueError` from reportlab's paraparser ("saw </b>
instead of expected </para>"), surfacing as an unhandled 500 on every future
`GET /export.pdf` for that briefing until the offending item is removed. A symbol like
`"TSLA <script>x</script>"` doesn't crash but silently strips/reorders rendered
content instead.

Per `CLAUDE.md`: "No tests during the hackathon... If a bug needs a regression test
mid-hackathon, add a minimal pytest test next to the code under test" — this is that
minimal test, not the start of a suite. Drives the real `GET /export.pdf` endpoint via
`TestClient` (not just the renderer directly) so it reproduces the exact failure mode
reported: an unhandled 500 at the HTTP layer, not just a renderer-level exception.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api.v1.dependencies import (
    get_briefing_repository,
    get_signal_repository,
    get_watchlist_repository,
    require_current_user,
)
from app.api.v1.schemas import CurrentUser
from app.domain.briefing.entities import Briefing, BriefingInstrumentSection
from app.domain.briefing.ports import BriefingRepository
from app.domain.review.entities import OpenReviewItem, ReviewedEntityType, ReviewState
from app.domain.signals.entities import Signal
from app.domain.signals.ports import SignalRepository
from app.domain.watchlist.entities import Watchlist, WatchlistItem
from app.domain.watchlist.ports import WatchlistRepository
from app.main import app

# Explicitly overridden below via `require_current_user` — must not depend on whichever
# environment happens to run this test (dev-fallback only applies when
# SUPABASE_JWT_SECRET is unset; a real secret configured in this environment would
# otherwise 401 every request since no bearer token is ever sent).
_USER_ID = "dev-user"
_WATCHLIST_ID = "watchlist-1"
_BRIEFING_ID = "briefing-1"


class _FakeWatchlistRepository(WatchlistRepository):
    """Satisfies the constructor; only `get` is exercised by the export endpoint."""

    def __init__(self, watchlist: Watchlist) -> None:
        self._watchlist = watchlist

    async def create(self, watchlist: Watchlist) -> Watchlist:
        raise NotImplementedError

    async def get(self, watchlist_id: str) -> Watchlist | None:
        return self._watchlist if watchlist_id == self._watchlist.id else None

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        raise NotImplementedError

    async def list_all(self) -> list[Watchlist]:
        raise NotImplementedError

    async def rename(self, watchlist_id: str, name: str) -> Watchlist:
        raise NotImplementedError

    async def reorder(self, user_id: str, ordered_ids: list[str]) -> None:
        raise NotImplementedError

    async def delete(self, watchlist_id: str) -> None:
        raise NotImplementedError

    async def list_items(self, watchlist_id: str) -> list[WatchlistItem]:
        raise NotImplementedError

    async def add_item(self, watchlist_id: str, symbol: str) -> WatchlistItem:
        raise NotImplementedError

    async def remove_item(self, watchlist_id: str, item_id: str) -> None:
        raise NotImplementedError


class _EmptySignalRepository(SignalRepository):
    """The export route's enrichment finds no signals — labels stay raw-id shaped."""

    async def create(self, signal: Signal) -> Signal:
        raise NotImplementedError

    async def get(self, signal_id: str) -> Signal | None:
        return None

    async def get_by_ids(self, signal_ids: Sequence[str]) -> dict[str, Signal]:
        return {}

    async def list_for_instrument(self, symbol: str) -> list[Signal]:
        raise NotImplementedError

    async def get_latest_for_instrument(self, symbol: str, locale: str) -> Signal | None:
        raise NotImplementedError

    async def prune_for_instrument(self, symbol: str, locale: str, keep: int) -> int:
        raise NotImplementedError

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        raise NotImplementedError

    async def list_review_states(self, signal_id: str) -> list[ReviewState]:
        raise NotImplementedError


class _FakeBriefingRepository(BriefingRepository):
    """Satisfies the constructor; only `get` is exercised by the export endpoint."""

    def __init__(self, briefing: Briefing) -> None:
        self._briefing = briefing

    async def create(self, briefing: Briefing) -> Briefing:
        raise NotImplementedError

    async def get(self, briefing_id: str) -> Briefing | None:
        return self._briefing if briefing_id == self._briefing.id else None

    async def list_for_watchlist(self, watchlist_id: str) -> list[Briefing]:
        raise NotImplementedError

    async def get_latest_for_watchlist(self, watchlist_id: str) -> Briefing | None:
        raise NotImplementedError

    async def save_review_state(self, review_state: ReviewState) -> ReviewState:
        raise NotImplementedError

    async def list_review_states(self, briefing_id: str) -> list[ReviewState]:
        raise NotImplementedError


def _build_briefing(symbol: str) -> Briefing:
    """A `Briefing` shaped like issue #16's fuller document, with one instrument
    section carrying the given (possibly malicious) `symbol` — everything else
    exercises the original em-dash/content-extraction regression from the first pass.
    """
    return Briefing(
        id=_BRIEFING_ID,
        watchlist_id=_WATCHLIST_ID,
        summary="Executive summary grounded in linked signals.",
        disclaimer="This is not personalized financial advice.",
        instrument_breakdown=[
            BriefingInstrumentSection(
                symbol=symbol,
                narrative="Narrative grounded strictly in underlying signals.",
                evidence_sources=["Reuters — market wrap"],
            )
        ],
        open_review_items=[
            OpenReviewItem(entity_type=ReviewedEntityType.SIGNAL, entity_id="signal-1"),
        ],
        created_at=datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
    )


def _export_pdf_text(briefing: Briefing) -> tuple[int, bytes | None, str]:
    """Drive the real `GET /export.pdf` endpoint via `TestClient` for `briefing` and
    return `(status_code, response_bytes_or_none, extracted_text)`.
    """
    watchlist = Watchlist(id=_WATCHLIST_ID, user_id=_USER_ID, name="Tech watchlist")
    app.dependency_overrides[get_briefing_repository] = lambda: _FakeBriefingRepository(briefing)
    app.dependency_overrides[get_watchlist_repository] = lambda: _FakeWatchlistRepository(watchlist)
    app.dependency_overrides[get_signal_repository] = lambda: _EmptySignalRepository()
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id=_USER_ID, email="dev@example.com"
    )
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/briefings/{briefing.id}/export.pdf")
    finally:
        app.dependency_overrides.clear()

    if response.status_code != 200:
        return response.status_code, None, ""

    reader = PdfReader(BytesIO(response.content))
    text = "\n".join(page.extract_text() for page in reader.pages)
    return response.status_code, response.content, text


def test_symbol_with_closing_bold_tag_no_longer_crashes_and_renders_literally() -> None:
    """Reviewer-reported crash: `"AAPL</b>"` used to throw reportlab's paraparser
    `ValueError` ("saw </b> instead of expected </para>"), surfacing as an unhandled
    500. Must now render as literal text, not be interpreted as markup.
    """
    briefing = _build_briefing(symbol="AAPL</b>")

    status_code, pdf_bytes, text = _export_pdf_text(briefing)

    assert status_code == 200
    assert pdf_bytes is not None
    assert pdf_bytes.startswith(b"%PDF-")
    assert "AAPL</b>" in text


def test_symbol_with_script_tag_no_longer_strips_or_reorders_content() -> None:
    """A symbol like `"TSLA <script>x</script>"` didn't crash reportlab, but silently
    stripped/reordered rendered content when unescaped. Must render as literal text.
    """
    briefing = _build_briefing(symbol="TSLA <script>x</script>")

    status_code, pdf_bytes, text = _export_pdf_text(briefing)

    assert status_code == 200
    assert pdf_bytes is not None
    assert "TSLA <script>x</script>" in text
    # Content after the malicious symbol must still be present and un-reordered —
    # this is exactly what silently broke before the fix.
    assert "Narrative grounded strictly in underlying signals." in text


def test_original_content_extraction_regression_still_passes() -> None:
    """Re-run of the first pass's verification: the em-dash open-review-item label
    (literal "—", not the `&mdash;` XML entity — see `_build_open_review_items`'s
    comment) and full-content extraction across summary/instrument/disclaimer must
    still render correctly after this fix.
    """
    briefing = _build_briefing(symbol="AAPL")

    status_code, pdf_bytes, text = _export_pdf_text(briefing)

    assert status_code == 200
    assert pdf_bytes is not None
    assert briefing.summary in text
    assert "AAPL" in text
    assert briefing.instrument_breakdown[0].narrative in text
    assert briefing.instrument_breakdown[0].evidence_sources[0] in text
    assert "Signal — signal-1" in text
    assert briefing.disclaimer in text
