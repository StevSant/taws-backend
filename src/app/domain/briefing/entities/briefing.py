from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.briefing.entities.briefing_instrument_section import BriefingInstrumentSection
from app.domain.review.entities import OpenReviewItem


@dataclass(slots=True)
class Briefing:
    """An Advisor-agent-produced summary for one watchlist, grounded in linked signals.

    Written by the Advisor agent (issue #3), on-demand or on a scheduled daily run
    (issue #10's `RunDailyBriefings`). `disclaimer` is a product invariant (never
    personalized advice), persisted here.

    Fuller document structure (issue #16, extending the T0 "basic" shape above):

    - `summary` doubles as the document's **executive summary** — a short LLM-composed
      overview grounded in the watchlist's signals. Reused rather than duplicated into a
      new `executive_summary` field: it already served exactly this purpose in the T0
      shape, just without the richer structure alongside it.
    - `instrument_breakdown` is the **per-instrument breakdown**: one
      `BriefingInstrumentSection` per tracked instrument, with its own narrative, impact
      classes, and evidence.
    - `linked_signal_ids` (T0, unchanged) already covers **linked signals/evidence** — no
      redundant field added.
    - `open_review_items` is the **open review items** list: signals and prior briefings
      for this watchlist that have no recorded reviewer decision yet (see
      `GenerateBriefing._gather_open_review_items`).
    """

    id: str
    watchlist_id: str
    summary: str
    disclaimer: str
    linked_signal_ids: list[str] = field(default_factory=list)
    instrument_breakdown: list[BriefingInstrumentSection] = field(default_factory=list)
    open_review_items: list[OpenReviewItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
