from app.domain.event_intelligence.entities import NewsEvent
from app.domain.market.entities import NewsItem


def news_event_from_news_item(item: NewsItem) -> NewsEvent:
    """Adapt one persisted radar article to Sentinel's Gemini input shape."""
    return NewsEvent(
        title=item.title,
        description=item.summary,
        content=item.summary,
        source=item.source,
        url=item.url,
        published_at=item.published_at,
    )
