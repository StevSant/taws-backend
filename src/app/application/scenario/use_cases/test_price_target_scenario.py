from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from app.application.scenario.extract_scenario_numeric_intent import (
    extract_scenario_numeric_intent,
)
from app.application.scenario.scenario_spec_extraction import ScenarioSpecExtraction
from app.application.scenario.use_cases.compute_scenario_quantification import (
    ComputeScenarioQuantification,
)
from app.domain.market.entities import AssetClass, Instrument, PriceCandle, PriceSeries
from app.domain.scenario.entities import (
    ScenarioDirection,
    ScenarioHorizon,
    ScenarioMagnitude,
    ScenarioSpec,
)


def test_scenario_extraction_preserves_numeric_intent() -> None:
    extraction = ScenarioSpecExtraction.model_validate(
        {
            "is_market_relevant": True,
            "entity": "Bitcoin",
            "event_type": "price_shock",
            "magnitude": "high",
            "horizon": "immediate",
            "title": "Bitcoin falls to $40,000 tomorrow",
            "description": "Bitcoin reaches a price of $40,000 tomorrow.",
            "target_price": 40_000,
            "direction": "down",
            "timeframe_days": 1,
            "affected_symbols": ["BTC"],
        }
    )

    assert extraction.target_price == 40_000
    assert extraction.direction == ScenarioDirection.DOWN
    assert extraction.timeframe_days == 1


def test_spanish_natural_language_numeric_intent_is_deterministic() -> None:
    target, direction, days = extract_scenario_numeric_intent(
        "¿Qué pasaría si Bitcoin cae a 40 mil dólares mañana?"
    )

    assert target == 40_000
    assert direction == ScenarioDirection.DOWN
    assert days == 1


async def test_scenario_quantification_uses_target_move_and_forward_returns() -> None:
    instrument = Instrument(
        symbol="BTC",
        name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        currency="USD",
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    closes = [100.0, 70.0, 77.0, 77.0, 50.0, 55.0, 55.0, 55.0, 55.0]
    candles = [
        PriceCandle(
            timestamp=start + timedelta(days=index),
            open=close,
            high=close,
            low=close,
            close=close,
        )
        for index, close in enumerate(closes)
    ]
    provider = Mock()
    provider.get_last_price = AsyncMock(return_value=100.0)
    provider.get_price_series = AsyncMock(return_value=PriceSeries(symbol="BTC", candles=candles))
    universe = Mock()
    universe.by_symbol = Mock(return_value=instrument)
    spec = ScenarioSpec(
        entity="Bitcoin",
        event_type="price_shock",
        magnitude=ScenarioMagnitude.HIGH,
        horizon=ScenarioHorizon.IMMEDIATE,
        title="Bitcoin falls to 70 tomorrow",
        description="Bitcoin reaches 70 tomorrow.",
        target_price=70,
        direction=ScenarioDirection.DOWN,
        timeframe_days=1,
        affected_symbols=["BTC"],
        affected_asset_classes=[AssetClass.CRYPTO],
    )

    results = await ComputeScenarioQuantification(provider, universe).execute(spec)

    stats = results["BTC"]
    assert stats.move_threshold_pct == 25.0
    assert stats.sample_size == 2
    assert stats.forward_1d_median_pct == 10.0
    assert stats.scenario_probability_pct == 25.0
    assert stats.scenario_probability_sample_size == 8
    assert stats.scenario_probability_occurrences == 2
