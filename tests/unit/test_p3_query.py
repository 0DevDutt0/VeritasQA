"""P3 query building: the normalized phrase is one quoted FTS5 string, and its characters map back to the raw phrase."""

from __future__ import annotations

import re

import pytest

from app.common.errors import QueryError
from app.retrieval.query import MATCH_COLUMN, build_phrase_query

ONE_QUOTED_STRING = re.compile(r'^index_text : "(?:[^"]|"")*"$')

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
    "a\"\"b",
]


@pytest.mark.parametrize(
    ("phrase", "match"),
    [
        ("3.5", 'index_text : "3.5"'),
        ("ABC-123", 'index_text : "ABC-123"'),
        ("risk assessment", 'index_text : "risk assessment"'),
        ("  risk\tassessment  ", 'index_text : "risk assessment"'),
        ("“quoted”", 'index_text : """quoted"""'),
        ("ﬁle", 'index_text : "file"'),
        ("café", 'index_text : "café"'),
        ("مرحبا بالعالم", 'index_text : "مرحبا بالعالم"'),
        ("文字の認識", 'index_text : "文字の認識"'),
    ],
)
def test_the_normalized_phrase_is_one_quoted_fts_string(phrase, match):
    assert build_phrase_query(phrase).match == match


def test_the_column_filter_is_fixed():
    assert MATCH_COLUMN == "index_text"
    assert build_phrase_query("risk").match.startswith('index_text : "')


@pytest.mark.parametrize("phrase", HOSTILE)
def test_hostile_text_stays_inside_one_quoted_string(phrase):
    query = build_phrase_query(phrase)
    assert ONE_QUOTED_STRING.match(query.match), query.match


def test_a_quote_inside_the_phrase_is_doubled_and_never_closes_the_string():
    query = build_phrase_query('say "x"')
    assert query.match == 'index_text : "say ""x"""'
    assert ONE_QUOTED_STRING.match(query.match)


def test_the_mapping_returns_the_raw_range_of_each_normalized_character():
    phrase = "ﬁ “x”"  # ligature fi, no-break space, curly quotes around x
    query = build_phrase_query(phrase)
    assert query.normalized == 'fi "x"'
    assert query.raw_range(0, 2) == (0, 1)  # both characters of the ligature come from raw char 0
    assert query.raw_range(2, 3) == (1, 2)  # the space comes from the no-break space
    assert query.raw_range(3, 4) == (2, 3)  # the straight quote comes from the left curly quote
    assert query.raw_range(4, 5) == (3, 4)
    assert phrase[query.raw_range(4, 5)[0] : query.raw_range(4, 5)[1]] == "x"
    assert query.raw_range(0, len(query.normalized)) == (0, len(phrase))


def test_the_raw_phrase_is_kept_beside_the_query():
    assert build_phrase_query("Risk  Assessment").phrase == "Risk  Assessment"


@pytest.mark.parametrize("phrase", ["risk\x00", "risk\x07assessment", "\x1bx"])
def test_control_characters_are_refused(phrase):
    with pytest.raises(QueryError, match="control character"):
        build_phrase_query(phrase)


def test_whitespace_control_characters_are_spaces_not_refusals():
    assert build_phrase_query("risk\tassessment").normalized == "risk assessment"


@pytest.mark.parametrize("phrase", ["", "   ", "!!!", "-", "...", '""', "^", "*", "%_%", "́"])
def test_a_phrase_without_letters_or_digits_is_refused(phrase):
    with pytest.raises(QueryError, match="no letter or digit"):
        build_phrase_query(phrase)


@pytest.mark.parametrize("value", [3, None, b"risk"])
def test_a_phrase_that_is_not_text_is_refused(value):
    with pytest.raises(QueryError, match="must be text"):
        build_phrase_query(value)


@pytest.mark.parametrize("phrase", ["risk\ud800", "\udfffrisk", "ri\ud83dsk"])
def test_a_lone_surrogate_is_refused_as_a_query_error_not_a_raw_error(phrase):
    with pytest.raises(QueryError, match="not valid Unicode"):
        build_phrase_query(phrase)
