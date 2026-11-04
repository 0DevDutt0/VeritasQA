"""P3 phrase search on a stored document: candidate step, exact check, isolation and determinism.

The sample document is hand-built (tests/fixtures/store_records.py), so each expected unit is known.
The brute-force reference applies only the exact check to every body unit. The FTS candidate step must
never miss a unit that the exact check accepts.
"""

from __future__ import annotations

import pytest

from app.common.errors import QueryError, StorageError
from app.document_structure.models import ContentType
from app.retrieval import find_phrase
from app.retrieval.query import build_phrase_query
from app.storage import Store
from tests.fixtures.store_checks import brute_force_phrase, row_counts
from tests.fixtures.store_records import DOC_A, DOC_B, PAGE_ONE, PAGE_TWO, sample_document

CREATED = "2026-01-01T00:00:00Z"


@pytest.fixture()
def store(tmp_path):
    handle = Store.open(tmp_path / "store.sqlite")
    extracted_a, structure_a = sample_document(DOC_A)
    extracted_b, structure_b = sample_document(DOC_B)
    handle.write_document(extracted_a, structure_a, created_at=CREATED)
    handle.write_document(extracted_b, structure_b, created_at=CREATED)
    yield handle
    handle.close()


def _ids(store, document_id, phrase):
    return [unit.evidence_id for unit in find_phrase(store, document_id, phrase)]


def _unit_id(document_id, page, ordinal):
    return f"{document_id}:p{page:04d}:u{ordinal:04d}"


# Ordinals on page one: 1 heading, 2 threshold, 3 numbers, 4 "Risk. assessment", 5 "risk and assessment",
# 6 "assessment of the risk", 7 identifiers, 8 café/cafe, 9 footer. On page two: 1 row, 2 cell, 3 paragraph.
EXPECTED = [
    ("3.5", [_unit_id(DOC_A, 1, 2), _unit_id(DOC_A, 2, 3)]),
    ("threshold is 3.5", [_unit_id(DOC_A, 1, 2), _unit_id(DOC_A, 2, 3)]),
    ("3 5", []),
    ("3 . 5", []),
    ("13.5", [_unit_id(DOC_A, 1, 3)]),
    ("3.55", [_unit_id(DOC_A, 1, 3)]),
    ("3.5.2", [_unit_id(DOC_A, 1, 3)]),
    ("5", []),
    ("risk assessment", [_unit_id(DOC_A, 1, 1)]),
    ("risk and assessment", [_unit_id(DOC_A, 1, 5)]),
    ("risk AND assessment", [_unit_id(DOC_A, 1, 5)]),
    ("Guide", [_unit_id(DOC_A, 1, 1)]),
    ("Guide Overview", []),
    ("assessment", [_unit_id(DOC_A, 1, 1), _unit_id(DOC_A, 1, 4), _unit_id(DOC_A, 1, 5), _unit_id(DOC_A, 1, 6)]),
    ("ABC-123", [_unit_id(DOC_A, 1, 7)]),
    ("ABC 123", [_unit_id(DOC_A, 1, 7)]),
    ("café", [_unit_id(DOC_A, 1, 8)]),
    ("cafe", [_unit_id(DOC_A, 1, 8)]),
    ("Page 1", []),
    ("Low 1", []),
    ("Rating = 1", []),
    ("Low", [_unit_id(DOC_A, 2, 1)]),  # the cell unit's own text is "1"; "Low" is only in the row
]


@pytest.mark.parametrize(("phrase", "expected"), EXPECTED, ids=[phrase for phrase, _ in EXPECTED])
def test_phrase_search_returns_the_expected_units(store, phrase, expected):
    assert _ids(store, DOC_A, phrase) == expected


def test_results_come_back_in_page_and_ordinal_order(store):
    results = find_phrase(store, DOC_A, "assessment")
    keys = [(unit.pdf_page, unit.ordinal) for unit in results]
    assert keys == sorted(keys)


def test_repeated_searches_return_identical_results(store):
    first = find_phrase(store, DOC_A, "assessment")
    second = find_phrase(store, DOC_A, "assessment")
    assert first == second


def test_a_search_never_returns_another_documents_units(store):
    results = find_phrase(store, DOC_A, "threshold is 3.5")
    assert results and all(unit.document_id == DOC_A for unit in results)
    other = find_phrase(store, DOC_B, "threshold is 3.5")
    assert {unit.document_id for unit in other} == {DOC_B}
    assert {unit.evidence_id for unit in results}.isdisjoint({unit.evidence_id for unit in other})


def test_a_heading_word_does_not_match_the_body_units_under_it(store):
    results = _ids(store, DOC_A, "Guide")
    assert results == [_unit_id(DOC_A, 1, 1)]


def test_header_and_footer_units_are_never_returned(store):
    footer_id = _unit_id(DOC_A, 1, 9)
    assert footer_id not in _ids(store, DOC_A, "Page 1 of 2")
    assert footer_id not in _ids(store, DOC_A, "Page")


def test_a_derived_row_is_a_candidate_only_when_its_source_text_matches(store):
    row_id = _unit_id(DOC_A, 2, 1)
    assert row_id not in _ids(store, DOC_A, "Rating = 1")
    assert row_id not in _ids(store, DOC_A, "Low 1")
    assert row_id in _ids(store, DOC_A, "Low")
    row = next(unit for unit in find_phrase(store, DOC_A, "Low") if unit.evidence_id == row_id)
    assert row.derived is True
    assert row.content_type == ContentType.TABLE_ROW


def test_a_phrase_in_one_span_of_a_multi_span_unit_is_found(store):
    results = find_phrase(store, DOC_A, "Rare")
    assert _unit_id(DOC_A, 2, 1) in [unit.evidence_id for unit in results]


def test_a_slice_of_a_units_own_text_finds_that_unit(store):
    for unit in store.match_units(DOC_A, build_phrase_query("threshold").match):
        for start, end in unit.source_spans:
            fragment = PAGE_ONE[start:end] if unit.pdf_page == 1 else PAGE_TWO[start:end]
            words = fragment.split()
            if len(words) >= 2:
                phrase = " ".join(words[:2])
                assert unit.evidence_id in _ids(store, DOC_A, phrase), (unit.evidence_id, phrase)


@pytest.mark.parametrize("phrase", [phrase for phrase, _ in EXPECTED] + ["the", "of the", "risk", "3.5 for"])
def test_the_candidate_step_never_misses_a_unit_the_exact_check_accepts(store, phrase):
    via_search = sorted(_ids(store, DOC_A, phrase))
    assert via_search == brute_force_phrase(store, DOC_A, phrase)


HOSTILE = [
    "risk AND assessment",
    "risk OR assessment",
    "NOT risk",
    "NEAR(a b)",
    "-risk",
    "risk*",
    "a:b",
    "^x",
    "(risk)",
    '"risk',
    "'); DROP TABLE evidence_units; --",
    "{index_text} : risk",
    "index_text : secret",
    "x\\y",
]


@pytest.mark.parametrize("phrase", HOSTILE)
def test_hostile_queries_are_literal_and_leave_the_store_unchanged(store, phrase):
    before = row_counts(store)
    results = find_phrase(store, DOC_A, phrase)
    assert isinstance(results, list)
    assert row_counts(store) == before


def test_operators_are_literal_words_not_boolean_logic(store):
    assert _ids(store, DOC_A, "risk AND assessment") == [_unit_id(DOC_A, 1, 5)]
    assert _unit_id(DOC_A, 1, 6) not in _ids(store, DOC_A, "risk AND assessment")


@pytest.mark.parametrize("phrase", ["", "   ", "!!!", "*", "^", '"', "%_%"])
def test_a_phrase_with_no_letters_or_digits_raises(store, phrase):
    with pytest.raises(QueryError):
        find_phrase(store, DOC_A, phrase)


def test_an_unknown_document_is_an_error_not_an_empty_result(store):
    with pytest.raises(StorageError, match="holds no document"):
        find_phrase(store, "doc-" + "f" * 16, "threshold")


def test_identical_text_under_two_document_ids_never_leaks(store):
    a = _ids(store, DOC_A, "threshold is 3.5 for high risk")
    b = _ids(store, DOC_B, "threshold is 3.5 for high risk")
    assert a and b
    assert all(evidence_id.startswith(DOC_A) for evidence_id in a)
    assert all(evidence_id.startswith(DOC_B) for evidence_id in b)
