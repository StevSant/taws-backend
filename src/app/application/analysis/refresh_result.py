from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RefreshResult:
    """Outcome of one `RefreshTrackedAnalysis` pass (issue #29).

    `refreshed` counts `(symbol, locale)` pairs the pass touched successfully — note this
    includes pairs whose analysis was already fresh and therefore cost nothing, since the
    freshness gate lives inside the generate use cases and is invisible from here. `failed`
    counts pairs whose generation raised; one failure never aborts the pass.

    Returned by both the scheduled tick (logged) and `POST /api/v1/analysis/refresh` (serialized),
    so an operator can tell a working refresh from a silently-failing one.
    """

    symbols: int
    locales: int
    refreshed: int
    failed: int
