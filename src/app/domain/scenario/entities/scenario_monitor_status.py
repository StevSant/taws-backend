from enum import StrEnum


class ScenarioMonitorStatus(StrEnum):
    """Lifecycle state of an armed `ScenarioMonitor` (issue #18).

    - `ARMED`: watching — Watchdog's scheduled evaluation pass checks it every tick.
    - `MATCHED`: a materializing signal/price-move was detected and a Telegram alert was
      sent; stays matched-and-quiet rather than auto-disarming (see `ScenarioMonitor`'s
      docstring for why) — Watchdog's evaluation pass skips it going forward.
    - `EXPIRED`: its TTL (`Settings.scenario_monitor_ttl_days`) elapsed with no match;
      also skipped going forward. The user can re-arm to reset it back to `ARMED`.
    """

    ARMED = "armed"
    MATCHED = "matched"
    EXPIRED = "expired"
