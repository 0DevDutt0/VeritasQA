"""P4 term extraction: numbers, percentages, dates and identifiers in query text (ARCHITECTURE §13, D43)."""

from __future__ import annotations

import pytest

from app.retrieval.terms import TermKind, extract_terms


def _pairs(text: str) -> list[tuple[TermKind, str]]:
    return [(term.kind, term.text) for term in extract_terms(text)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3.5", [(TermKind.NUMBER, "3.5")]),
        ("10%", [(TermKind.PERCENT, "10%")]),
        ("10 %", [(TermKind.PERCENT, "10 %")]),
        ("2024-01-01", [(TermKind.DATE, "2024-01-01")]),
        ("ABC-123", [(TermKind.IDENTIFIER, "ABC-123")]),
        ("4 March 2024", [(TermKind.DATE, "4 March 2024")]),
        ("March 4, 2024", [(TermKind.DATE, "March 4, 2024")]),
        ("1,250", [(TermKind.NUMBER, "1,250")]),
        ("version 2.1.0", [(TermKind.NUMBER, "2.1.0")]),
    ],
)
def test_each_kind_is_found_as_one_whole_term(text, expected):
    assert _pairs(text) == expected


def test_a_date_takes_precedence_over_the_numbers_inside_it():
    assert _pairs("on 2024-01-01 we") == [(TermKind.DATE, "2024-01-01")]


def test_a_percentage_takes_precedence_over_its_number():
    assert _pairs("limit 10% now") == [(TermKind.PERCENT, "10%")]


def test_an_identifier_takes_precedence_over_its_digits():
    assert _pairs("see ABC-123") == [(TermKind.IDENTIFIER, "ABC-123")]


@pytest.mark.parametrize("text", ["well-known", "risk-based", "a-b"])
def test_hyphenated_words_without_digits_are_not_identifiers(text):
    assert all(kind is not TermKind.IDENTIFIER for kind, _ in _pairs(text))


def test_a_hyphenated_number_range_is_two_numbers():
    # "800-30" has no letter, so it is not an identifier. Each side is a number.
    assert _pairs("800-30") == [(TermKind.NUMBER, "800"), (TermKind.NUMBER, "30")]


def test_offsets_point_at_the_term_text():
    text = "Use 3.5 and ABC-123 today, on 2024-01-01."
    for term in extract_terms(text):
        assert text[term.start : term.end] == term.text


def test_terms_come_in_order_of_position():
    assert [term.text for term in extract_terms("3.5 and 2024-01-01 and ABC-123")] == [
        "3.5",
        "2024-01-01",
        "ABC-123",
    ]


def test_plain_words_have_no_terms():
    assert extract_terms("risk assessment guide") == ()


def test_a_digit_inside_a_word_is_not_a_term():
    assert extract_terms("v2x and abc3") == ()
