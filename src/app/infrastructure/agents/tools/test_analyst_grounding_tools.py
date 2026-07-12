from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.domain.signals.entities import ImpactClass, Signal, SignalEvidence
from app.infrastructure.agents.tools.generate_signal_tool import build_generate_signal_tool
from app.infrastructure.agents.tools.get_news_tool import build_get_news_tool


async def test_get_news_tool_returns_dated_sourced_evidence() -> None:
    provider = Mock()
    provider.fetch_news = AsyncMock(
        return_value=[
            SimpleNamespace(
                title="Chip exports face new restrictions",
                summary="New controls affect advanced accelerators.",
                source="Reuters",
                provider="finnhub",
                url="https://example.com/chips",
                published_at=datetime(2026, 7, 12, 14, 30, tzinfo=UTC),
                related_symbols=["NVDA"],
            )
        ]
    )

    output = await build_get_news_tool(provider).ainvoke({"symbol": "nvda", "limit": 3})

    provider.fetch_news.assert_awaited_once_with(symbols=["NVDA"], limit=3)
    assert "2026-07-12T14:30:00+00:00" in output
    assert "Reuters: Chip exports face new restrictions" in output
    assert "related symbols: NVDA" in output
    assert "https://example.com/chips" in output


async def test_get_news_tool_prioritizes_stories_linked_to_tracked_instruments() -> None:
    provider = Mock()
    provider.fetch_news = AsyncMock(
        return_value=[
            SimpleNamespace(
                title="General mobility story",
                summary="No tracked company is identified.",
                source="Publisher",
                provider="rss",
                url="https://example.com/mobility",
                published_at=datetime(2026, 7, 12, 15, 0, tzinfo=UTC),
                related_symbols=[],
            ),
            SimpleNamespace(
                title="Nvidia accelerator demand rises",
                summary="Demand increased.",
                source="Reuters",
                provider="finnhub",
                url="https://example.com/nvda",
                published_at=datetime(2026, 7, 12, 14, 0, tzinfo=UTC),
                related_symbols=["NVDA"],
            ),
        ]
    )

    output = await build_get_news_tool(provider).ainvoke({"limit": 1})

    provider.fetch_news.assert_awaited_once_with(symbols=None, limit=5)
    assert "Nvidia accelerator demand rises" in output
    assert "General mobility story" not in output


async def test_generate_signal_tool_exposes_rag_pipeline_result() -> None:
    signal = Signal(
        id="sig-1",
        instrument_symbol="NVDA",
        impact_class=ImpactClass.NEGATIVE,
        confidence=0.74,
        evidence=[
            SignalEvidence(
                source="Reuters",
                published_at=datetime(2026, 7, 12, 14, 30, tzinfo=UTC),
                url="https://example.com/chips",
                detail="New export restrictions",
            )
        ],
        disclaimer="Research context only.",
        thesis="Restrictions may constrain near-term accelerator sales.",
        key_drivers=["Export controls"],
        risk_factors=["Policy reversal"],
    )
    use_case = Mock()
    use_case.execute = AsyncMock(return_value=signal)

    output = await build_generate_signal_tool(use_case, "es").ainvoke({"symbol": "nvda"})

    use_case.execute.assert_awaited_once_with("NVDA", "es")
    assert "impact: negative" in output
    assert "confidence: 74%" in output
    assert "Reuters: New export restrictions" in output
    assert "Research context only." in output
