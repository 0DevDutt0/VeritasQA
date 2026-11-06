"""P15: the comparison text rule (ARCHITECTURE §20.3). Line breaks and spacing do not count; other changes do."""

from app.comparison.text import normalize_page_text


def test_spaces_and_line_breaks_are_collapsed_to_single_spaces():
    assert normalize_page_text("The limit  is\n30 days\t.") == "The limit is 30 days ."


def test_leading_and_trailing_whitespace_is_trimmed():
    assert normalize_page_text("  \n Hello world \n ") == "Hello world"


def test_a_hyphen_at_a_line_end_is_joined_to_the_next_line():
    assert normalize_page_text("infor-\nmation") == "information"
    assert normalize_page_text("infor-\r\n   mation") == "information"


def test_a_unicode_hyphen_and_a_soft_hyphen_at_a_line_end_are_joined_too():
    assert normalize_page_text("infor‐\nmation") == "information"
    assert normalize_page_text("infor­\nmation") == "information"


def test_a_hyphen_inside_a_line_is_kept():
    assert normalize_page_text("well-known rule") == "well-known rule"


def test_case_digits_and_punctuation_still_count():
    assert normalize_page_text("Limit 30 days.") != normalize_page_text("limit 30 days.")
    assert normalize_page_text("Limit 30 days.") != normalize_page_text("Limit 31 days.")
    assert normalize_page_text("Limit 30 days.") != normalize_page_text("Limit 30 days")


def test_an_empty_or_blank_page_normalizes_to_the_empty_string():
    assert normalize_page_text("") == ""
    assert normalize_page_text(" \n\t ") == ""
