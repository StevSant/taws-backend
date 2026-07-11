from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain.market.entities import AssetClass, NewsItem
from app.domain.market.ports import NewsProvider
from app.infrastructure.seeds import load_news_fixture_seed


class FixtureNewsProvider(NewsProvider):
    """NewsProvider adapter serving the packaged news fixture.

    Timestamps are relative (`hours_ago` in the seed JSON) and converted to
    absolute UTC datetimes on every call, so fixture items always look fresh
    relative to "now" instead of aging while the process stays up. Used as the
    `AggregatingNewsProvider` fallback when no live source is configured/available.
    """

    def __init__(self, seed_path: Path) -> None:
        self._seed_path = seed_path

    async def fetch_news(
        self,
        symbols: list[str] | None = None,
        asset_class: AssetClass | None = None,
        since_hours: int = 48,
        limit: int = 50,
    ) -> list[NewsItem]:
        del asset_class  # asset-class filtering happens centrally in the aggregator
        rows = load_news_fixture_seed(self._seed_path)
        now = datetime.now(UTC)
        items = [
            NewsItem(
                id=row["id"],
                title=row["title"],
                summary=row["summary"],
                url=row["url"],
                source=row["source"],
                published_at=now - timedelta(hours=row["hours_ago"]),
                related_symbols=list(row.get("related_symbols", [])),
            )
            for row in rows
        ]
        items = [item for item in items if now - item.published_at <= timedelta(hours=since_hours)]
        if symbols:
            wanted = {symbol.upper() for symbol in symbols}
            items = [
                item for item in items if wanted & {sym.upper() for sym in item.related_symbols}
            ]
        items.sort(key=lambda item: item.published_at, reverse=True)
        return items[:limit]
