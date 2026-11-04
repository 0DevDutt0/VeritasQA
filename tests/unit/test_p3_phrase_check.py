"""P3 exact check (ARCHITECTURE §12): table-driven positive and negative cases for ``span_matches``.

The rules are word boundaries, numeric boundaries, spacing and punctuation, case, and diacritics.
The cases marked "pinned limit" fix behaviour that is a known limitation, so a change to it is visible.
"""

from __future__ import annotations

import pytest

from app.retrieval.phrase import fold_case, span_matches
from app.retrieval.query import build_phrase_query

CASES = [
    # --- numbers: a decimal number is one token, and its neighbours decide
    ("3.5", "3.5", True),
    ("3.5", "value 3.5 applies", True),
    ("3.5", "3.5%", True),
    ("3.5", "see 3.5.", True),
    ("3.5", "3 5", False),
    ("3.5", "3 . 5", False),
    ("3.5", "3,5", False),
    ("3.5", "13.5", False),
    ("3.5", "3.55", False),
    ("3.5", "3.5.2", False),
    ("3.5", "1,3.5", False),
    ("3.5", "x3.5", False),
    ("3", "3.5", False),
    ("5", "3.5", False),
    ("5", "5", True),
    ("3.5", "-3.5", True),  # pinned limit: the sign is left to the P6 value check
    ("-5", "a -5 b", True),
    ("-5", "3-5", False),
    (".5", "3.5", False),
    ("U.S.", "U.S.A", False),
    ("U.S.", "in the U.S. today", True),
    # --- words, spacing and punctuation
    ("risk assessment", "Risk Assessment", True),
    ("risk assessment", "risk assessment", True),
    ("risk assessment", "risk\nassessment", True),
    ("risk assessment", "risk. assessment", False),
    ("risk assessment", "risk assessments", False),
    ("risk assessment", "a risk assessment.", True),
    ("risk", "risk-based", True),
    ("risk", "riskier", False),
    ("risk", "at risk.", True),
    ("risk assessment", "risk​assessment", False),
    ("3.5", "3.5­", True),
    ("ABC 123", "ABC-123", False),
    ("ABC-123", "ABC-123", True),
    ("ABC", "ABC_123", False),
    # --- case and diacritics
    ("cafe", "café", False),
    ("café", "CAFÉ", True),
    ("Ångström", "ångström", True),
    # --- scripts without spaces, and combining marks
    ("文字の認識", "文字の認識 を行う", True),
    ("مرحبا", "مرحبا بالعالم", True),
    ("مرحبا", "أهلا مرحبا", True),
    ("مرحبا", "مرحباً", False),
    ("文字", "文字の認識", False),  # pinned limit: a phrase inside a run of letters has no boundary
    ("İstanbul", "istanbul", False),  # pinned limit: 'İ'.lower() has two characters, so it is kept
]


@pytest.mark.parametrize(("phrase", "text", "expected"), CASES, ids=[f"{p!r}-in-{t!r}" for p, t, _ in CASES])
def test_exact_check(phrase, text, expected):
    assert span_matches(text, build_phrase_query(phrase)) is expected


def test_an_empty_span_matches_nothing():
    assert span_matches("", build_phrase_query("risk")) is False


def test_a_match_is_found_after_an_earlier_rejected_occurrence():
    text = "13.5 then 3.5 again"
    assert span_matches(text, build_phrase_query("3.5")) is True


@pytest.mark.parametrize(
    "text",
    ["ÀÉÎÕÜ", "Straße", "İ", "ǅ", "ΑΒΓΣ", "ЖИВ", "مرحبا", "文字", "́e", "Å"],
)
def test_case_folding_keeps_the_length(text):
    assert len(fold_case(text)) == len(text)


def test_case_folding_is_per_character_and_keeps_the_others():
    assert fold_case("ÀÉÎ") == "àéî"
    assert fold_case("İ") == "İ"
    assert fold_case("Risk") == "risk"
