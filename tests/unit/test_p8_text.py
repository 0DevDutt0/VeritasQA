"""The P8a text rule (ARCHITECTURE §17.1, D76): any run of whitespace is one space, and nothing else changes."""

from app.evaluation.text import contains, normalize, tokens

PAGE = "The limit for loans is 30 days after approval."


def test_a_run_of_whitespace_becomes_one_space():
    assert normalize("30  days\n after\tapproval ") == "30 days after approval"


def test_a_line_break_matches_a_space():
    assert contains("The limit for loans is 30\ndays after approval.", "The limit for loans is 30 days after approval.")


def test_a_no_break_space_is_whitespace():
    assert normalize("30 days") == "30 days"


def test_a_true_substring_is_verbatim():
    assert contains(PAGE, "The limit for loans is 30 days")


def test_case_is_compared_exactly():
    assert not contains(PAGE, "the limit for loans is 30 days after approval.")


def test_one_changed_digit_is_refused():
    assert not contains(PAGE, "The limit for loans is 31 days after approval.")


def test_one_changed_punctuation_mark_is_refused():
    assert not contains(PAGE, "The limit for loans is 30 days after approval!")


def test_a_blank_needle_never_occurs():
    assert not contains("anything at all", "   ")


def test_tokens_are_word_characters_in_order():
    assert tokens("30 days, 5 USD.") == ["30", "days", "5", "USD"]
