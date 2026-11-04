"""P6 vocabulary and the value-occurrence rule (ARCHITECTURE §15, D62 to D64)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.evidence.selection import RULE_IDS
from app.question_processing.analysis import QuestionType
from app.verification.terms import find_occurrences
from app.verification.vocabulary import (
    ANSWER_TYPES,
    BLOCKING_FLAG_REASONS,
    EXPECTED_RULE_IDS,
    HEDGE,
    NEGATION,
    STRONG_QUALIFIERS,
)

SELECTION_SOURCE = Path(__file__).resolve().parents[2] / "app" / "evidence" / "selection.py"


def test_expected_rule_ids_are_the_p5_rules():
    assert EXPECTED_RULE_IDS == RULE_IDS


def test_answer_types_are_the_three_types_whose_rule_can_give_a_span():
    assert ANSWER_TYPES == {QuestionType.WHEN, QuestionType.HOW_MANY, QuestionType.WHETHER}


def test_every_flag_that_p5_sets_is_a_blocking_flag():
    # The flags are read from the P5 source, so a flag added there without a row here fails this test.
    set_in_p5 = set(re.findall(r'flags\.append\("([a-z_]+)"\)', SELECTION_SOURCE.read_text(encoding="utf-8")))
    assert set_in_p5, "the flag pattern found nothing, so the test would pass for the wrong reason"
    assert set_in_p5 <= set(BLOCKING_FLAG_REASONS)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("This applies unless the loan is renewed.", "unless"),
        ("The rule does\nnot apply here.", "does\nnot apply"),
        ("Payment is due, subject to approval.", "subject to"),
    ],
)
def test_strong_qualifiers_match_whole_phrases(text, expected):
    match = STRONG_QUALIFIERS.search(text)
    assert match is not None and match.group(0) == expected


@pytest.mark.parametrize("text", ["An exceptional case.", "This is accepted.", "Unlessly stated."])
def test_strong_qualifiers_do_not_match_inside_a_word(text):
    assert STRONG_QUALIFIERS.search(text) is None


@pytest.mark.parametrize("text, expected", [("The staff isn't eligible.", "n't"), ("No loans.", "No")])
def test_negation_words_and_the_contraction(text, expected):
    match = NEGATION.search(text)
    assert match is not None and match.group(0) == expected


@pytest.mark.parametrize("text", ["Annotated text.", "A knot in the rope."])
def test_negation_does_not_match_inside_a_word(text):
    assert NEGATION.search(text) is None


def test_hedges_mark_uncertainty_but_not_the_policy_phrase_may_be():
    assert HEDGE.search("The fee might apply.") is not None
    assert HEDGE.search("The equipment may be used by staff.") is None


@pytest.mark.parametrize(
    "text, term, expected",
    [
        ("The cap is 3.5 days.", "3.5", [False]),
        ("The cap is -3.5 days.", "3.5", [True]),
        ("The cap is (-3.5) days.", "3.5", [True]),
        ("The cap is −3.5 days.", "3.5", [True]),
        ("From –3.5 days.", "3.5", [True]),
        ("Apply 10-15 days.", "15", [False]),
        ("Apply 10 - 15 days.", "15", [False]),
        ("Apply 30 days.", "30", [False]),
        ("Dated 2024-01-01.", "2024-01-01", [False]),
        ("See ABC-123.", "ABC-123", [False]),
        ("A 10% fee.", "10%", [False]),
        ("January\n5, 2024 applies.", "January 5, 2024", [False]),
        ("Pay 30 days.", "30", [False]),
        ("The cap is 3.5", "3.5", [False]),
        ("-3.5 and 3.5 days.", "3.5", [True, False]),
    ],
)
def test_a_value_occurs_with_its_sign_and_its_boundaries(text, term, expected):
    assert [occurrence.negative for occurrence in find_occurrences(text, term)] == expected


@pytest.mark.parametrize(
    "text, term",
    [
        ("The code is 3.5.2 here.", "3.5"),  # a longer identifier
        ("Items 1,2,3 apply.", "2"),  # a list of numbers
        ("The fee is 15 days.", "5"),  # the end of a longer number
        ("The rate is 13.5 days.", "3.5"),  # the end of a longer decimal
        ("Apply 130 days.", "30"),
        ("See XABC-123.", "ABC-123"),
        ("A 110% fee.", "10%"),
        ("The cap is 3 5 days.", "3.5"),  # a space is not a decimal point
    ],
)
def test_a_value_inside_a_longer_token_does_not_occur(text, term):
    assert find_occurrences(text, term) == ()


def test_an_empty_term_occurs_nowhere():
    assert find_occurrences("The cap is 3.5 days.", "   ") == ()
