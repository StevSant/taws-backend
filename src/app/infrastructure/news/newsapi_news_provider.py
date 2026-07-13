import logging
from datetime import datetime

import httpx

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import NewsProvider
from app.infrastructure.caching import CooldownGate

logger = logging.getLogger(__name__)

# Status codes that mean "this won't succeed again on the next poll" — a config/quota
# problem (401 covers apiKeyInvalid/Missing/Disabled *and* apiKeyExhausted on NewsAPI,
# 426 upgradeRequired is a plan limit) — or a rate limit (429). A transient network
# error or a 5xx is handled by the per-call catch-and-degrade path without a breaker.
_NON_TRANSIENT_STATUS_CODES = frozenset({401, 426, 429})
_RATE_LIMIT_STATUS_CODE = 429


class NewsApiNewsProvider(NewsProvider):
    """NewsProvider adapter backed by the NewsAPI.org `/everything` endpoint.

    Returns items with empty `related_symbols` — NewsAPI doesn't tag instruments
    itself, so linking is done centrally by `AggregatingNewsProvider`. Without an
    API key it returns no items instead of crashing.

    Circuit breaker (mirrors Marketaux, issue #9): the NewsAPI free tier caps at 100
    requests/day, and `GET /api/v1/news` fans out to this adapter on *every* poll, so
    once the quota/rate limit is hit every subsequent request re-hits an already-failing
    API and gets another 401/426/429 — one 429 turns into a per-poll storm. `_cooldown`
    gates `fetch_news` shut for `rate_limit_cooldown_seconds` (429, usually clears sooner)
    or `cooldown_seconds` (401/426, quota/plan issues that won't clear soon) after such a
    response, logging exactly one warning per cool-down instead of one per skipped poll.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        default_query: str,
        timeout_seconds: float = 10.0,
        cooldown_seconds: float = 1200.0,
        rate_limit_cooldown_seconds: float = 300.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._default_query = default_query
        self._timeout_seconds = timeout_seconds
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
        del asset_class  # NewsAPI has no asset-class filter; done centrally in the aggregator
        if not self._api_key or self._cooldown.is_open():
            return []

        query = " OR ".join(symbols) if symbols else self._default_query
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": min(limit, 100),
        }
        # Send the key via the `X-Api-Key` header (NewsAPI supports it) rather than the
        # `apiKey` query param, so the secret never lands in a logged request URL (issue #45).
        headers = {"X-Api-Key": self._api_key}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds
            ) as client:
                response = await client.get("/everything", params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            self._handle_status_error(exc)
            return []

        items: list[NewsItem] = []
        for article in payload.get("articles", []):
            item = self._to_news_item(article)
            if item is not None:
                items.append(item)
        return items[:limit]

    def _handle_status_error(self, exc: httpx.HTTPStatusError) -> None:
        """Trip the circuit breaker on a non-transient status, else let it re-raise.

        The `X-Api-Key` header keeps the secret out of the request URL, so the httpx
        error message (which only echoes the URL) is safe to log verbatim (issue #45).
        """
        status_code = exc.response.status_code
        if status_code not in _NON_TRANSIENT_STATUS_CODES:
            raise exc
        cooldown_seconds = (
            self._rate_limit_cooldown_seconds
            if status_code == _RATE_LIMIT_STATUS_CODE
            else self._cooldown_seconds
        )
        self._cooldown.trip(cooldown_seconds, f"NewsAPI returned {status_code}: {exc}")

    @staticmethod
    def _to_news_item(article: dict) -> NewsItem | None:
        try:
            source = article.get("source") or {}
            published_raw = article.get("publishedAt") or ""
            return NewsItem(
                id=article.get("url") or "",
                title=article.get("title") or "",
                summary=article.get("description") or "",
                url=article.get("url") or "",
                source=source.get("name") or "NewsAPI",
                provider="newsapi",
                published_at=datetime.fromisoformat(published_raw.replace("Z", "+00:00")),
                related_symbols=[],
                image_url=article.get("urlToImage") or None,
            )
        except (KeyError, ValueError, TypeError):
            return None
