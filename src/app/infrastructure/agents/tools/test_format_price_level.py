from app.infrastructure.agents.tools.format_price_level import format_price_level


def test_groups_btc_scale_value_without_scientific_notation() -> None:
    # Regression: a plain ``:.4g`` rendered this as "6.492e+04", which reads as invented.
    result = format_price_level(64920.0)

    assert result == "64,920.00"
    assert "e" not in result


def test_keeps_two_decimals_for_mid_range_price() -> None:
    assert format_price_level(580.3) == "580.30"


def test_keeps_meaningful_precision_for_sub_dollar_token() -> None:
    assert format_price_level(0.0034) == "0.0034"


def test_never_collapses_a_tiny_value_to_zero() -> None:
    result = format_price_level(0.00034)

    assert result == "0.00034"
    assert "e" not in result


def test_pads_fractional_value_to_at_least_two_decimals() -> None:
    assert format_price_level(0.5) == "0.50"


def test_formats_zero_plainly() -> None:
    assert format_price_level(0.0) == "0.00"
