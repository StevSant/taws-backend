from typing import Any

from app.domain.scenario.entities import ScenarioMonitor, ScenarioMonitorStatus
from app.infrastructure.persistence.parse_supabase_timestamp import parse_supabase_timestamp


def scenario_monitor_to_row(monitor: ScenarioMonitor) -> dict[str, Any]:
    """Map a `ScenarioMonitor` onto the row shape stored in `scenario_monitors`."""
    return {
        "id": monitor.id,
        "scenario_id": monitor.scenario_id,
        "user_id": monitor.user_id,
        "status": monitor.status.value,
        "armed_at": monitor.armed_at.isoformat(),
        "expires_at": monitor.expires_at.isoformat(),
        "matched_at": monitor.matched_at.isoformat() if monitor.matched_at else None,
        "match_reason": monitor.match_reason,
        "created_at": monitor.created_at.isoformat(),
    }


def scenario_monitor_from_row(row: Any) -> ScenarioMonitor:
    """Map one `scenario_monitors` table row (as returned by `supabase-py`) onto
    `ScenarioMonitor`. Typed `Any` rather than `dict[str, Any]` — see
    `watchlist_row_mapper.py` for why."""
    return ScenarioMonitor(
        id=row["id"],
        scenario_id=row["scenario_id"],
        user_id=row["user_id"],
        status=ScenarioMonitorStatus(row["status"]),
        armed_at=parse_supabase_timestamp(row["armed_at"]),
        expires_at=parse_supabase_timestamp(row["expires_at"]),
        matched_at=parse_supabase_timestamp(row["matched_at"]) if row.get("matched_at") else None,
        match_reason=row.get("match_reason"),
        created_at=parse_supabase_timestamp(row["created_at"]),
    )
