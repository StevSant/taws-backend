def format_price_level(value: float) -> str:
    """Format a price or index level for user-facing prose: thousands separators and
    adaptive decimals, never scientific notation.

    A plain ``:.4g`` collapses BTC-scale numbers to ``6.492e+04``, which reads as machine
    output — or invented data — to a non-technical user. This keeps large values grouped
    (``64,920.00``) and small sub-dollar values meaningful (``0.0034``) without ever
    emitting an exponent.
    """
    magnitude = abs(value)
    if magnitude >= 1 or magnitude == 0:
        return f"{value:,.2f}"

    # Sub-$1 instruments: keep enough decimals to stay meaningful (a flat ``.2f`` would
    # render a $0.0034 token as "0.00"), then trim noise zeros without dropping below two.
    decimals = 4 if magnitude >= 0.01 else 8
    integer_part, _, fractional_part = f"{value:,.{decimals}f}".partition(".")
    fractional_part = fractional_part.rstrip("0").ljust(2, "0")
    return f"{integer_part}.{fractional_part}"
