"""Review domain: reviewer decisions (reviewed/escalated/discarded) on signals and briefings.

Shared by `domain/signals/` and `domain/briefing/` — a `ReviewState` always references
either a `Signal` or a `Briefing` by id, never a trading/execution record. Persistence is
exposed as a primitive on `SignalRepository`/`BriefingRepository` (`save_review_state`);
the review *use case* (issue #4) is out of scope here.
"""
