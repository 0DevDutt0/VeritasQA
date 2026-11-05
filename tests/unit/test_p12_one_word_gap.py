"""P12 (D129, option 2): one word between a number and its counted noun (ARCHITECTURE §14).

The rule is checked on synthetic sentences only. The development gate is a separate, recorded run on scratch copies
of the stores (PROGRESS.md, P12). The span checks below pin what the answer text becomes: selection takes a how-many
answer span from the value's text, so the word between the number and the noun is part of the answer.
"""

import pytest

from app.evidence.values import find_values


def _values(text: str, nouns: tuple[str, ...] = ("members",)):
    return find_values(text, count_nouns=nouns)


def test_one_word_between_number_and_noun_links_and_is_part_of_the_value() -> None:
    text = "A total of 12 current members joined."
    (value,) = _values(text)
    assert value.text == "12 current members"
    assert value.unit == "members"
    assert text[value.start : value.end] == value.text


def test_the_linked_word_is_in_the_span_that_selection_uses_as_the_answer() -> None:
    # Selection gives a how-many answer the value's own text (app/evidence/selection.py, _candidate), so the word is
    # part of the answer. An expected answer without the word is therefore not matched under exact scoring (D113).
    (value,) = _values("Fifty staff joined. A total of 12 current members joined.")
    assert value.text == "12 current members"


def test_a_singular_form_of_the_counted_noun_links_through_one_word() -> None:
    (value,) = _values("A total of 12 current member joined.")
    assert value.text == "12 current member"
    assert value.unit == "members"


def test_a_line_break_may_separate_the_number_and_the_word() -> None:
    text = "A total of 12\ncurrent members joined."
    (value,) = _values(text)
    assert value.text == "12\ncurrent members"
    assert value.unit == "members"


def test_a_hyphen_may_separate_the_number_and_the_word() -> None:
    (value,) = _values("A total of 12-current members joined.")
    assert value.text == "12-current members"
    assert value.unit == "members"


def test_two_words_between_number_and_noun_do_not_link() -> None:
    (value,) = _values("A total of 12 current new members joined.")
    assert value.text == "12"
    assert value.unit is None


@pytest.mark.parametrize(
    "word",
    [
        # function words
        "of",
        "the",
        "than",
        "for",
        # question words
        "which",
        "how",
        # negations
        "not",
        "no",
        # cardinal number words
        "three",
        "twelve",
        "hundred",
    ],
)
def test_a_function_question_negation_or_number_word_does_not_link(word: str) -> None:
    (value,) = _values(f"There were 12 {word} members here.")
    assert value.text == "12"
    assert value.unit is None


def test_a_number_as_the_word_between_does_not_link() -> None:
    # The number 2024 is a value of its own, and it links to the noun directly. The 12 is not linked through it.
    values = _values("There were 12 2024 members here.")
    assert [(value.text, value.unit) for value in values] == [("12", None), ("2024 members", "members")]


@pytest.mark.parametrize(
    "text",
    [
        "The panel met on 12. Current members voted.",
        "There were 12 people. Current members voted.",
        "There were 12! Current members voted.",
    ],
)
def test_a_number_in_a_neighbouring_sentence_does_not_link(text: str) -> None:
    values = _values(text)
    assert values, "the number is still a bare value"
    assert all(value.unit is None for value in values)


def test_a_capitalised_counted_noun_still_does_not_count() -> None:
    # The noun rule of D59 is unchanged: the noun must be lower case as written.
    (value,) = _values("A total of 12 current Members joined.")
    assert value.text == "12"
    assert value.unit is None


def test_a_dotted_number_still_does_not_count() -> None:
    # A dotted number is a section number (D59), even when a word and a counted noun follow it.
    values = _values("The rule 3.2 current members apply.")
    assert all(value.unit is None for value in values)


def test_a_number_that_opens_the_text_still_does_not_count() -> None:
    # The D59 rule for a number at the start of a text is unchanged.
    (value,) = _values("12 current members joined.")
    assert value.text == "12"
    assert value.unit is None


def test_the_immediate_noun_rule_is_unchanged() -> None:
    (value,) = _values("A total of 12 members of staff joined.")
    assert value.text == "12 members"
    assert value.unit == "members"


def test_without_count_nouns_no_word_is_linked() -> None:
    (value,) = find_values("A total of 12 current members joined.")
    assert value.text == "12"
    assert value.unit is None
