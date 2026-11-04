"""P3 query building: tokens come from the normalized phrase, and the MATCH expression stays literal."""

from __future__ import annotations

import re

import pytest

from app.common.errors import QueryError
from app.retrieval.query import MATCH_COLUMN, build_phrase_query

MATCH_SHAPE = re.compile(r'^index_text : "[^\W_]+( [^\W_]+)*"$')

HOSTILE = [
    "risk AND assessment",
    "risk OR assessment",
    "NOT risk",
    "NEAR(a b)",
    "NEAR(a b, 3)",
    "-risk",
    "risk*",
    "a:b",
    "index_text:secret",
    "^x",
    "(risk)",
    '"risk',
    'risk"',
    "'); DROP TABLE evidence_units; --",
    "{index_text} : risk",
    "3.5 AND 3.5*",
    "x\\y",
]


@pytest.mark.parametrize(
    ("phrase", "tokens"),
    [
        ("3.5", ("3", "5")),
        ("ABC-123", ("ABC", "123")),
        ("ABC_123", ("ABC", "123")),
        ("café", ("café",)),
        ("ﬁle name", ("file", "name")),
        ("  risk assessment  ", ("risk", "assessment")),
        ("مرحبا بالعالم", ("مرحبا", "بالعالم")),
        ("文字の認識", ("文字の認識",)),
        ("Ångström", ("Ångström",)),
    ],
)
def test_tokens_come_from_the_normalized_phrase(phrase, tokens):
    assert build_phrase_query(phrase).tokens == tokens


def test_the_match_expression_has_a_fixed_column_filter_and_one_quoted_phrase():
    query = build_phrase_query("risk assessment")
    assert query.match == f'{MATCH_COLUMN} : "risk assessment"' == 'index_text : "risk assessment"'
    assert query.normalized == "risk assessment"
    assert query.phrase == "risk assessment"


@pytest.mark.parametrize("phrase", HOSTILE)
def test_hostile_text_becomes_literal_tokens_only(phrase):
    query = build_phrase_query(phrase)
    assert MATCH_SHAPE.match(query.match), query.match
    assert all(token.isalnum() or re.fullmatch(r"[^\W_]+", token) for token in query.tokens)


def test_operators_are_turned_into_plain_words():
    assert build_phrase_query("risk AND assessment").tokens == ("risk", "AND", "assessment")
    assert build_phrase_query("NEAR(a b)").tokens == ("NEAR", "a", "b")
    assert build_phrase_query("3.5 AND 3.5*").match == 'index_text : "3 5 AND 3 5"'


@pytest.mark.parametrize("phrase", ["", "   ", "!!!", "-", "...", "\"\"", "^", "*", "%_%"])
def test_a_phrase_without_letters_or_digits_is_refused(phrase):
    with pytest.raises(QueryError, match="no letter or digit"):
        build_phrase_query(phrase)


@pytest.mark.parametrize("value", [3, None, b"risk"])
def test_a_phrase_that_is_not_text_is_refused(value):
    with pytest.raises(QueryError, match="must be text"):
        build_phrase_query(value)
