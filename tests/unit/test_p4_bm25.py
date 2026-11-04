"""P4 BM25 candidates on synthetic documents: ranking direction, column weights, limits, exact terms,
per-document statistics, scope and refusals (ARCHITECTURE §13, D39-D43).

Every ranking test runs on a document in which no query term occurs in half of the units. Otherwise FTS5
clamps the IDF to 1e-6 and the scores tie (see tests/fixtures/retrieval_docs.py). The fixture checks this.
"""

from __future__ import annotations

import math

import pytest

from app.common.errors import QueryError, StorageError
from app.retrieval import search
from app.retrieval.bm25 import ColumnWeights
from app.storage import Store
from tests.fixtures.retrieval_docs import (
    DOC_LARGE,
    DOC_LARGE_TWIN,
    Item,
    assert_idf_is_informative,
    build,
    filler,
    large_document,
    ranking_items,
)

CREATED = "2026-01-01T00:00:00Z"
TERMS = ("threshold", "assessment", "quarterly")
HOSTILE = [
    "risk AND assessment",
    "NEAR(a b)",
    "-risk",
    "risk*",
    "a:b",
    "^x",
    "(risk)",
    '"risk',
    "'); DROP TABLE evidence_units; --",
    "index_text : secret",
    "risk OR NOT assessment",
]
DOC_NUMERIC = "doc-" + "3" * 16


def _id(structure, fragment: str) -> str:
    matches = [unit.evidence_id for unit in structure.units if fragment in unit.raw_text]
    assert len(matches) == 1, f"{fragment!r} should name one unit, found {len(matches)}"
    return matches[0]


def _by_id(result):
    return {candidate.evidence_id: candidate for candidate in result.candidates}


def _numeric_items() -> list[Item]:
    return (
        filler(20, page=1)
        + [
            Item(page=1, text="The rate is 3.5 percent."),
            Item(page=1, text="The rate is 3.5.2 percent."),
            Item(page=1, text="The rate is 13.5 percent."),
            Item(page=1, text="Use ABC-123 here."),
            Item(page=1, text="Use ABC 123 here."),
            Item(page=1, text="Issued 2024-01-01 by the office."),
        ]
        + filler(20, page=1)
    )


@pytest.fixture(scope="module")
def large():
    extracted, structure = large_document()
    assert_idf_is_informative(structure, TERMS)
    store = Store.open(":memory:")
    store.write_document(extracted, structure, created_at=CREATED)
    yield store, structure
    store.close()


@pytest.fixture(scope="module")
def numeric():
    extracted, structure = build(DOC_NUMERIC, _numeric_items())
    store = Store.open(":memory:")
    store.write_document(extracted, structure, created_at=CREATED)
    yield store, structure
    store.close()


# ------------------------------------------------------------------ ranking direction and margins


def test_candidates_are_ranked_best_first_and_numbered_from_one(large):
    store, _ = large
    result = search(store, DOC_LARGE, "threshold assessment quarterly", k=50, context_window=0)
    assert [candidate.rank for candidate in result.candidates] == list(range(1, len(result.candidates) + 1))
    raw = [candidate.bm25_raw for candidate in result.candidates]
    assert raw == sorted(raw)
    assert all(value < 0 for value in raw), "FTS5 reports a better match as a smaller, negative value"


def test_a_unit_with_both_query_words_beats_a_unit_with_one_by_a_clear_margin(large):
    store, structure = large
    result = search(store, DOC_LARGE, "threshold assessment", context_window=0)
    both = _id(structure, "threshold used in the assessment")
    single = _id(structure, "The threshold is recorded")
    found = _by_id(result)
    assert found[both].rank == 1
    assert found[single].bm25_raw - found[both].bm25_raw > 1.0


def test_the_heading_weight_decides_whether_a_heading_only_match_ranks_first(large):
    store, structure = large
    heading_only = _id(structure, "Visits are logged")
    body_match = _id(structure, "The assessment covers quarterly reports")
    equal = _by_id(search(store, DOC_LARGE, "quarterly", context_window=0, weights=ColumnWeights(1.0, 1.0)))
    heavy = _by_id(search(store, DOC_LARGE, "quarterly", context_window=0, weights=ColumnWeights(1.0, 5.0)))
    light = _by_id(search(store, DOC_LARGE, "quarterly", context_window=0, weights=ColumnWeights(1.0, 0.01)))
    assert equal[body_match].rank < equal[heading_only].rank
    assert heavy[heading_only].rank < heavy[body_match].rank
    assert heavy[heading_only].bm25_raw < equal[heading_only].bm25_raw < light[heading_only].bm25_raw


def test_equal_scores_are_ordered_by_evidence_id(large):
    store, _ = large
    candidates = search(store, DOC_LARGE, "threshold", context_window=0).candidates
    ties = [(first, second) for first, second in zip(candidates, candidates[1:]) if first.bm25_raw == second.bm25_raw]
    assert ties, "the fixture must contain a tie so that the tiebreak is exercised"
    for first, second in ties:
        assert first.evidence_id < second.evidence_id


def test_a_word_that_no_unit_contains_gives_no_candidates(large):
    store, _ = large
    result = search(store, DOC_LARGE, "zebra")
    assert result.candidates == ()
    assert result.trace.original_hits == 0


def test_the_running_header_is_never_a_candidate(large):
    store, _ = large
    # The header text contains "header", but header units are not body units and are not indexed.
    assert search(store, DOC_LARGE, "header").candidates == ()


# ------------------------------------------------------------------ limits and overrides


def test_k_limits_the_candidates_and_the_trace_counts_the_rest(large):
    store, _ = large
    full = search(store, DOC_LARGE, "threshold assessment quarterly", k=50, context_window=0)
    limited = search(store, DOC_LARGE, "threshold assessment quarterly", k=2, context_window=0)
    assert [candidate.evidence_id for candidate in limited.candidates] == [
        candidate.evidence_id for candidate in full.candidates[:2]
    ]
    assert limited.trace.truncated_original == full.trace.original_hits - 2


def test_per_call_overrides_take_precedence_over_the_configuration(large):
    store, _ = large
    result = search(store, DOC_LARGE, "threshold", k=1, context_window=0, expansion_k=0)
    assert (result.trace.k, result.trace.context_window, result.trace.expansion_k) == (1, 0, 0)
    assert len(result.candidates) == 1


def test_the_same_question_gives_the_same_result(large):
    store, _ = large
    first = search(store, DOC_LARGE, "threshold assessment quarterly")
    second = search(store, DOC_LARGE, "threshold assessment quarterly")
    assert first == second


# ------------------------------------------------------------------ numbers, dates and identifiers


def test_a_number_matches_its_units_and_only_the_exact_form_is_reported(numeric):
    store, structure = numeric
    result = search(store, DOC_NUMERIC, "3.5", context_window=0)
    found = _by_id(result)
    exact_unit = _id(structure, "rate is 3.5 percent")
    superset_unit = _id(structure, "rate is 3.5.2 percent")
    assert found[exact_unit].exact_terms == ("3.5",)
    # FTS5 also matches "3.5.2" for the phrase "3 5". It is a candidate, but its exact form is not there.
    assert superset_unit in found
    assert found[superset_unit].exact_terms == ()
    # "13.5" has no adjacent "3" and "5" in the index, so it is not a candidate at all.
    assert _id(structure, "rate is 13.5 percent") not in found
    assert [term.text for term in result.trace.terms] == ["3.5"]


def test_an_identifier_is_reported_only_when_its_hyphenated_form_is_present(numeric):
    store, structure = numeric
    found = _by_id(search(store, DOC_NUMERIC, "ABC-123", context_window=0))
    assert found[_id(structure, "Use ABC-123 here")].exact_terms == ("ABC-123",)
    assert found[_id(structure, "Use ABC 123 here")].exact_terms == ()


def test_a_date_is_reported_when_its_exact_form_is_present(numeric):
    store, structure = numeric
    found = _by_id(search(store, DOC_NUMERIC, "2024-01-01", context_window=0))
    assert found[_id(structure, "Issued 2024-01-01")].exact_terms == ("2024-01-01",)


# ------------------------------------------------------------------ plain text and refusals


def test_hostile_query_text_is_plain_text_and_the_store_survives(large):
    store, structure = large
    for text in HOSTILE:
        assert isinstance(search(store, DOC_LARGE, text).candidates, tuple), text
    assert len(store.load_structure(DOC_LARGE).units) == len(structure.units)


@pytest.mark.parametrize("query", ["", "   ", "-- ?", "!!!", " "])
def test_a_query_without_letters_or_digits_is_refused(large, query):
    store, _ = large
    with pytest.raises(QueryError):
        search(store, DOC_LARGE, query)


@pytest.mark.parametrize("query", [None, 42, "risk\x00", "risk\x07"])
def test_a_query_that_is_not_text_or_has_a_control_character_is_refused(large, query):
    store, _ = large
    with pytest.raises(QueryError):
        search(store, DOC_LARGE, query)


def test_an_unknown_document_is_refused(large):
    store, _ = large
    with pytest.raises(StorageError):
        search(store, "doc-" + "f" * 16, "threshold")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k": 0},
        {"k": True},
        {"expansion_k": -1},
        {"context_window": -1},
        {"weights": ColumnWeights(0.0, 1.0)},
        {"weights": ColumnWeights(1.0, math.nan)},
        {"weights": ColumnWeights(1.0, math.inf)},
    ],
)
def test_out_of_range_arguments_are_refused(large, kwargs):
    store, _ = large
    with pytest.raises(ValueError):
        search(store, DOC_LARGE, "threshold", **kwargs)


# ------------------------------------------------------------------ per-document statistics and scope


def _twin_items() -> list[Item]:
    # The same wording as the large document, plus units that repeat the query terms. A statistic shared
    # across documents would change the IDF of "threshold" and "assessment" in the large document.
    return ranking_items() + [Item(page=1, text=f"Extra threshold note {number} on the assessment.") for number in range(12)]


def test_a_second_document_does_not_change_the_scores_of_the_first():
    extracted, structure = large_document()
    alone = Store.open(":memory:")
    together = Store.open(":memory:")
    try:
        alone.write_document(extracted, structure, created_at=CREATED)
        together.write_document(extracted, structure, created_at=CREATED)
        twin_extracted, twin_structure = build(DOC_LARGE_TWIN, _twin_items())
        together.write_document(twin_extracted, twin_structure, created_at=CREATED)
        for query in ("threshold assessment", "quarterly", "threshold", "threshold assessment quarterly"):
            assert search(alone, DOC_LARGE, query) == search(together, DOC_LARGE, query), query
    finally:
        alone.close()
        together.close()


def test_results_never_name_another_document():
    extracted, structure = large_document()
    store = Store.open(":memory:")
    try:
        store.write_document(extracted, structure, created_at=CREATED)
        twin_extracted, twin_structure = build(DOC_LARGE_TWIN, _twin_items())
        store.write_document(twin_extracted, twin_structure, created_at=CREATED)
        for query in ("threshold", "assessment", "quarterly"):
            for candidate in search(store, DOC_LARGE, query).candidates:
                assert candidate.evidence_id.startswith(DOC_LARGE + ":"), candidate.evidence_id
    finally:
        store.close()


def test_the_scratch_index_holds_exactly_the_body_rows_of_evidence_fts(large):
    store, _ = large
    with store.document_bm25_index(DOC_LARGE) as index:
        indexed = index.indexed_ids()
        row_count = index.row_count
    stored = {
        row[0]
        for row in store._conn.execute("SELECT evidence_id FROM evidence_fts WHERE document_id = ?", (DOC_LARGE,))
    }
    assert indexed == stored
    assert row_count == len(stored) > 0


def test_the_scratch_index_is_dropped_when_the_search_ends(large):
    store, _ = large
    search(store, DOC_LARGE, "threshold")
    leftover = store._conn.execute("SELECT name FROM sqlite_temp_master WHERE name = 'document_bm25'").fetchall()
    assert leftover == []


def test_two_document_indexes_cannot_be_open_at_once(large):
    store, _ = large
    with store.document_bm25_index(DOC_LARGE):
        with pytest.raises(StorageError, match="already open"):
            with store.document_bm25_index(DOC_LARGE):
                pass


def test_opening_an_index_for_an_unknown_document_is_refused(large):
    store, _ = large
    with pytest.raises(StorageError):
        with store.document_bm25_index("doc-" + "e" * 16):
            pass


def test_a_failed_index_build_leaves_no_temp_table_and_the_store_works_again():
    extracted, structure = large_document()
    store = Store.open(":memory:")
    try:
        store.write_document(extracted, structure, created_at=CREATED)
        # Hide the units table during the build, so that the insert fails after the index table was created.
        store._conn.execute("ALTER TABLE evidence_units RENAME TO evidence_units_hidden")
        try:
            with pytest.raises(StorageError, match="could not build"):
                with store.document_bm25_index(DOC_LARGE):
                    pass
        finally:
            store._conn.execute("ALTER TABLE evidence_units_hidden RENAME TO evidence_units")
        leftover = store._conn.execute("SELECT name FROM sqlite_temp_master WHERE name = 'document_bm25'").fetchall()
        assert leftover == []
        assert search(store, DOC_LARGE, "threshold").candidates
    finally:
        store.close()
