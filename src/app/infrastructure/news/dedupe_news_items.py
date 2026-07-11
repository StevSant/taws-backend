from app.domain.market.entities import NewsItem


def dedupe_news_items(items: list[NewsItem]) -> list[NewsItem]:
    """Remove duplicate news items, keyed by URL first and normalized title second."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    deduped: list[NewsItem] = []
    for item in items:
        normalized_title = item.title.strip().lower()
        if item.url in seen_urls or normalized_title in seen_titles:
            continue
        seen_urls.add(item.url)
        seen_titles.add(normalized_title)
        deduped.append(item)
    return deduped
