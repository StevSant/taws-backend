from app.infrastructure.notes import truncate_label


def test_short_text_is_returned_unchanged() -> None:
    assert truncate_label("Short summary", max_chars=60) == "Short summary"


def test_long_text_is_cut_at_a_word_boundary_and_ellipsized() -> None:
    text = "The crypto market shows weakness after the CPI print came in hotter than expected"
    result = truncate_label(text, max_chars=40)

    assert result == "The crypto market shows weakness after…"
    assert len(result) <= 41  # 40 + the ellipsis


def test_text_with_no_space_before_the_limit_is_cut_hard() -> None:
    assert truncate_label("A" * 80, max_chars=10) == "AAAAAAAAAA…"


def test_surrounding_whitespace_is_stripped() -> None:
    assert truncate_label("  padded  ", max_chars=60) == "padded"
