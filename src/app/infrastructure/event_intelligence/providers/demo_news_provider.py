from datetime import UTC, datetime

from app.domain.event_intelligence.entities import NewsEvent
from app.domain.event_intelligence.ports import NewsProviderPort

_DEMO_NEWS: list[NewsEvent] = [
    NewsEvent(
        title="Fed Holds Rates Steady, Signals Cautious Approach",
        description="The Federal Reserve maintained its benchmark interest rate at 5.25-5.50% "
        "and indicated a cautious stance on future cuts.",
        content="The Federal Reserve held interest rates steady at 5.25-5.50% during its latest "
        "meeting, citing persistent inflation concerns. Chair Powell noted that while progress "
        "has been made on inflation, the committee needs more evidence before considering rate "
        "cuts. Markets reacted with mild volatility as traders adjusted their rate-cut "
        "expectations for 2025.",
        source="Demo",
        url="https://example.com/fed-rates",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Tech Sector Surges on AI Earnings Optimism",
        description="Major technology stocks rallied after strong earnings reports from "
        "leading AI companies exceeded analyst expectations.",
        content="The technology sector saw broad gains today as several major companies "
        "reported better-than-expected quarterly earnings, driven by continued growth in "
        "AI-related revenue streams. NVIDIA, Microsoft, and Alphabet all posted gains. "
        "Analysts have revised their price targets upward, citing sustained demand for "
        "AI infrastructure and enterprise adoption.",
        source="Demo",
        url="https://example.com/tech-earnings",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Oil Prices Drop Amid Global Demand Concerns",
        description="Crude oil prices fell sharply as new economic data from major "
        "economies suggested slowing demand.",
        content="Oil prices declined over 3% following weaker-than-expected manufacturing "
        "data from China and Europe. Traders are concerned that global economic growth may be "
        "slowing more rapidly than anticipated, reducing near-term demand for crude. OPEC+ has "
        "not signaled any production adjustments at this time.",
        source="Demo",
        url="https://example.com/oil-prices",
        published_at=datetime.now(UTC),
    ),
]


class DemoNewsProvider(NewsProviderPort):
    """Returns a small set of hardcoded demo news events for testing the pipeline.

    Useful for development and demonstration without needing a real news API key.
    """

    async def fetch_latest_news(self) -> list[NewsEvent]:
        return list(_DEMO_NEWS)
