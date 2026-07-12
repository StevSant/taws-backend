from dataclasses import dataclass

from app.domain.market.entities.macro_indicator import MacroIndicator
from app.domain.market.entities.macro_observation import MacroObservation


@dataclass(frozen=True, slots=True)
class MacroSeries:
    """A historical run of observations for one macro indicator (oldest -> newest).

    Powers the "Contexto de mercado" sparklines with real history plus a time-range selector
    (issue #58). `observations` is ordered oldest-first; `latest` is the most recent reading.
    """

    indicator: MacroIndicator
    series_id: str
    observations: list[MacroObservation]

    @property
    def latest(self) -> MacroObservation | None:
        return self.observations[-1] if self.observations else None
