import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import NewsProvider
from app.infrastructure.caching import CooldownGate
from app.infrastructure.news.marketaux_article_mapper import map_marketaux_article
from app.infrastructure.news.marketaux_entity_types import ASSET_CLASS_TO_ENTITY_TYPES
from app.infrastructure.security import redact_url_secrets

logger = logging.getLogger(__name__)

# Status codes that mean "this won't succeed again on the next poll" — a config/billing
# problem (401 unauthorized, 402 quota exhausted) or a rate limit (429) — as opposed to
# a transient network error or a 5xx, which the existing per-call catch-and-degrade
# behavior already handles fine without a circuit breaker.
_NON_TRANSIENT_STATUS_CODES = frozenset({401, 402, 429})
_RATE_LIMIT_STATUS_CODE = 429


class MarketauxNewsProvider(NewsProvider):
    """NewsProvider adapter backed by the Marketaux news API.

    Marketaux identifies instruments inside each article and scores their
    sentiment, so every returned `NewsItem` carries `entities` and an
    article-level `sentiment_score` in addition to the HU1 basics.

    Guarded like the other vendor adapters: without an API key it returns an
    empty list instead of crashing. The free plan caps articles per request
    (3) and requests per day (100), so a fetch paginates at most `max_pages`
    times and callers are expected to cache results rather than hit this per
    user request.

    Circuit breaker (issue #9): a 401/402/429 response means retrying on the very
    next poll (typically ~60s later) has no realistic chance of succeeding — the
    quota/billing/rate-limit condition won't have cleared. `_cooldown` gates
    `fetch_news` shut for `cooldown_seconds` (401/402) or `rate_limit_cooldown_seconds`
    (429, usually shorter-lived) after such a response, logging exactly one warning per
    cool-down instead of repeating the failure on every poll — see `CooldownGate`.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        languages: str,
        timeout_seconds: float,
        max_pages: int,
        cooldown_seconds: float = 1200.0,
        rate_limit_cooldown_seconds: float = 300.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._languages = languages
        self._timeout_seconds = timeout_seconds
        self._max_pages = max_pages
        self._cooldown_seconds = cooldown_seconds
        self._rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._cooldown = CooldownGate()

    async def fetch_news(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        if not self._api_key or self._cooldown.is_open():
            return []

        params = self._build_params(symbols, asset_class, since_hours, limit)
        items: list[NewsItem] = []
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        ) as client:
            for page in range(1, self._max_pages + 1):
                payload = await self._fetch_page(client, params, page)
                if payload is None:
                    break
                articles = payload.get("data") or []
                items.extend(map_marketaux_article(article) for article in articles)
                if len(items) >= limit or self._is_last_page(payload, len(articles)):
                    break
        return items[:limit]

    def _build_params(
        self,
        symbols: list[str] | None,
        asset_class: AssetClass | None,
        since_hours: int,
        limit: int,
    ) -> dict[str, str]:
        published_after = datetime.now(UTC) - timedelta(hours=since_hours)
        params = {
            "api_token": self._api_key or "",
            "language": self._languages,
            # Only return articles with identified instruments, and only the
            # instruments matching the query — that's the enrichment we're here for.
            "filter_entities": "true",
            "must_have_entities": "true",
            "published_after": published_after.strftime("%Y-%m-%dT%H:%M"),
            "limit": str(limit),
        }
        if symbols:
            params["symbols"] = ",".join(symbols)
        entity_types = ASSET_CLASS_TO_ENTITY_TYPES.get(asset_class) if asset_class else None
        if entity_types:
            params["entity_types"] = entity_types
        return params

    async def _fetch_page(
        self, client: httpx.AsyncClient, params: dict[str, str], page: int
    ) -> dict | None:
        try:
            response = await client.get("/news/all", params={**params, "page": str(page)})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in _NON_TRANSIENT_STATUS_CODES:
                cooldown_seconds = (
                    self._rate_limit_cooldown_seconds
                    if status_code == _RATE_LIMIT_STATUS_CODE
                    else self._cooldown_seconds
                )
                self._cooldown.trip(
                    cooldown_seconds,
                    redact_url_secrets(
                        f"Marketaux returned {status_code}, pausing requests: {exc}"
                    ),
                )
            else:
                # Degrade gracefully so an aggregating provider can still serve other
                # sources; a 5xx here is treated as transient, not circuit-broken.
                logger.warning(
                    "Marketaux request failed (page %s): %s", page, redact_url_secrets(str(exc))
                )
            return None
        except httpx.HTTPError as exc:
            # Network-level errors (connect/timeout/etc) — transient, no circuit break.
            logger.warning(
                "Marketaux request failed (page %s): %s", page, redact_url_secrets(str(exc))
            )
            return None

    @staticmethod
    def _is_last_page(payload: dict, returned_count: int) -> bool:
        meta = payload.get("meta") or {}
        page_limit = int(meta.get("limit") or 0)
        return returned_count == 0 or returned_count < page_limit
