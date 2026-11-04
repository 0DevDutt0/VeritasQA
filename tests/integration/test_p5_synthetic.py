"""P5 end to end on a synthetic stored document: question -> analysis -> P4 search -> store -> selection (D54).

The document is written from hand-built records (labelled synthetic; no PDF is read), so every expected quote is
known. The check that matters is provenance: each quote equals the text stored for its page at the offsets that
selection reports. The stored page text is read back through ``Store.page_texts``, not taken from the unit.
"""

from __future__ import annotations

import pytest

from app.document_structure.models import ContentType
from app.evidence import ComponentStatus, select_candidates
from app.question_processing import analyze
from app.retrieval import search
from app.storage import Store
from tests.fixtures.retrieval_docs import Item, build, filler

DOC = "doc-" + "6" * 16
CREATED = "2026-01-01T00:00:00Z"

ITEMS = [
    Item(page=1, text="The board approves the loan for small businesses."),
    Item(page=1, text="The limit for loans is 30 days after approval."),
    *filler(12, page=1),
    Item(page=1, text="The fee for loans is 5 USD and the limit is 30 days."),
    Item(page=1, text="Staff must not share passwords with visitors."),
    Item(page=1, text="The fee is waived for staff. It applies unless the loan is renewed."),
    Item(page=1, text="Loans limit: 30 days", content_type=ContentType.TABLE_CELL),
    Item(
        page=1,
        text="Low | 1 | Rare",
        content_type=ContentType.TABLE_ROW,
        derived=True,
        index="Table 1 | Low | Rating = 1 ; Meaning = Rare",
    ),
]


@pytest.fixture(scope="module")
def stored():
    extracted, structure = build(DOC, ITEMS)
    store = Store.open(":memory:")
    store.write_document(extracted, structure, created_at=CREATED)
    yield store, store.page_texts(DOC, [1])
    store.close()


def _pipeline(store, question):
    analysis = analyze(question)
    retrieved = {}
    units = {}
    for component in analysis.components:
        if not component.searchable:
            continue
        result = search(store, DOC, component.retrieval_query, context_window=0)
        retrieved[component.component_id] = result
        for candidate in result.candidates:
            if candidate.evidence_id not in units:
                units[candidate.evidence_id] = store.load_unit(DOC, candidate.evidence_id)
    return analysis, select_candidates(analysis, retrieved, units)


def _quotes(selection, component_id="c1"):
    component = next(c for c in selection.components if c.component_id == component_id)
    return [candidate.quote for candidate in component.candidates]


def test_how_many_gives_the_stored_sentence_with_its_value_and_flags_the_two_quantity_sentence(stored):
    store, page = stored
    _, selection = _pipeline(store, "How many days is the limit for loans?")
    component = selection.components[0]
    assert component.status == ComponentStatus.CANDIDATES
    by_quote = {candidate.quote: candidate for candidate in component.candidates}

    single = by_quote["The limit for loans is 30 days after approval."]
    assert single.answer_span == "30 days"
    assert single.rule_id == "how_many.value_with_unit.v1"

    two = by_quote["The fee for loans is 5 USD and the limit is 30 days."]
    assert two.answer_span is None and "multiple_values" in two.flags

    cell = by_quote["Loans limit: 30 days"]
    assert cell.answer_span is None and "table_cell" in cell.flags

    for candidate in component.candidates:
        assert page[1][candidate.page_start : candidate.page_end] == candidate.quote
        if candidate.answer_span is not None:
            assert page[1][candidate.answer_page_start : candidate.answer_page_end] == candidate.answer_span


def test_a_permission_question_gives_the_stored_marker_and_its_polarity(stored):
    store, page = stored
    _, selection = _pipeline(store, "Is it permitted to share passwords?")
    candidate = selection.components[0].candidates[0]
    assert candidate.quote == "Staff must not share passwords with visitors."
    assert candidate.answer_span == "must not"
    assert candidate.negated is True
    assert page[1][candidate.answer_page_start : candidate.answer_page_end] == "must not"


def test_a_conditions_question_gives_the_whole_stored_paragraph(stored):
    store, page = stored
    _, selection = _pipeline(store, "Under what conditions is the fee waived for staff?")
    candidate = selection.components[0].candidates[0]
    assert candidate.granularity == "passage"
    assert candidate.quote == "The fee is waived for staff. It applies unless the loan is renewed."
    assert page[1][candidate.page_start : candidate.page_end] == candidate.quote


def test_a_derived_table_row_is_listed_as_dropped_and_never_quoted(stored):
    store, _ = stored
    _, selection = _pipeline(store, "What is the rating for low?")
    component = selection.components[0]
    assert ("derived_row" in [d.reason for d in component.dropped])
    assert all(candidate.quote != "Low | 1 | Rare" for candidate in component.candidates)
    assert all(not candidate.retrieval.derived for candidate in component.candidates)


def test_a_compound_question_reports_each_component_with_its_own_result(stored):
    store, _ = stored
    analysis, selection = _pipeline(
        store, "Is it permitted to share passwords? How many days is the limit for loans?"
    )
    assert [c.component_id for c in selection.components] == ["c1", "c2"]
    assert selection.components[0].status == ComponentStatus.CANDIDATES
    assert selection.components[1].status == ComponentStatus.CANDIDATES


def test_a_question_with_a_missing_subject_is_reported_and_not_searched(stored):
    store, _ = stored
    analysis, selection = _pipeline(store, "What is the fee and when is it due?")
    second = selection.components[1]
    assert second.status == ComponentStatus.AMBIGUOUS
    assert second.candidates == ()


def test_every_quote_in_the_stored_document_is_the_stored_text_at_its_offsets(stored):
    store, page = stored
    questions = [
        "What is the loan for small businesses?",
        "How many days is the limit for loans?",
        "When is the loan limit set?",
        "Is it permitted to share passwords?",
        "Under what conditions is the fee waived for staff?",
        "Which forms are required for the loan?",
    ]
    checked = 0
    for question in questions:
        _, selection = _pipeline(store, question)
        for component in selection.components:
            for candidate in component.candidates:
                assert page[1][candidate.page_start : candidate.page_end] == candidate.quote
                checked += 1
    assert checked > 0


def test_the_same_question_on_the_same_store_gives_the_same_selection(stored):
    store, _ = stored
    question = "How many days is the limit for loans?"
    _, first = _pipeline(store, question)
    _, second = _pipeline(store, question)
    assert first == second
