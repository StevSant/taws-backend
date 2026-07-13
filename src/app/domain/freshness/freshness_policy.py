from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType

from app.domain.market.entities import AssetClass


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """How long a persisted shared analysis counts as still current, per asset class (#29).

    A pure value object — no vendor imports, no I/O, no clock of its own (`now` is passed in
    so callers stay testable). The TTL map and the fallback are injected from `Settings` by
    `Container.get_freshness_policy()`; nothing here is hardcoded.

    Why a policy object rather than a bare `ttl_minutes` int threaded through every use case:
    the TTL is genuinely asset-class-dependent (crypto goes stale in minutes, equities in
    hours), and every gated pipeline — signals, sentiment, scenarios — needs to ask the exact
    same question. One value object keeps that question answered in one place, the same way
    `NewsPrefilterPolicy` (`application/signals/news_prefilter_policy.py`) already bundles the
    pre-filter's thresholds.

    `default_ttl` covers both the asset classes with no dedicated bucket (credit, commodity)
    and analyses that aren't about a single instrument at all (a preset scenario run), which
    pass `asset_class=None`.
    """

    ttl_by_asset_class: Mapping[AssetClass, timedelta]
    default_ttl: timedelta

    def __post_init__(self) -> None:
        # Freeze the injected mapping so a `FreshnessPolicy` handed to several use cases can
        # never be mutated through one of them — `frozen=True` alone wouldn't stop that.
        object.__setattr__(
            self, "ttl_by_asset_class", MappingProxyType(dict(self.ttl_by_asset_class))
        )

    def ttl_for(self, asset_class: AssetClass | None) -> timedelta:
        """Return the TTL for this asset class, falling back to `default_ttl`."""
        if asset_class is None:
            return self.default_ttl
        return self.ttl_by_asset_class.get(asset_class, self.default_ttl)

    def is_fresh(
        self,
        created_at: datetime,
        asset_class: AssetClass | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Whether an analysis created at `created_at` is still within its TTL.

        `now` defaults to the current UTC time; pass it explicitly to pin the clock. A
        naive `created_at` (no tzinfo) is read as UTC rather than raising — persisted rows
        always come back tz-aware from `parse_supabase_timestamp`, but an in-memory entity
        built by a fixture might not, and a `TypeError` deep inside a cache check is a worse
        failure than assuming the store's own timezone.
        """
        reference = now or datetime.now(UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return reference - created_at < self.ttl_for(asset_class)
