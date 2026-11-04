"""P5 selection on hand-built units (SPEC §6; ARCHITECTURE §14; D45-D49, D55).

Every page text, span and expected quote below is written out by hand, so each expected result is known. The
retrieval results are hand-built too: selection needs only the candidate's evidence ID, its flags and its
``via``, and the tests check that the retrieval object is kept by reference.
"""

from __future__ import annotations

import pytest

from app.document_structure.models import ContentType
from app.evidence import ComponentStatus, SelectionError, select_candidates
from app.question_processing import analyze
from app.retrieval.bm25 import ContextRef, RetrievalCandidate, RetrievalResult
from tests.fixtures.store_records import make_unit

DOC = "doc-" + "5" * 16


def _unit(ordinal, content_type, page_text, spans, *, derived=False, page=1):
    return make_unit(DOC, page, ordinal, content_type, page_text, spans, derived=derived)


def _retrieval(query, members):
    """A retrieval result for ``query``. ``members`` is a list of (unit, via) pairs, in rank order."""
    candidates = []
    for rank, (unit, via) in enumerate(members, start=1):
        candidates.append(
            RetrievalCandidate(
                rank=rank,
                evidence_id=unit.evidence_id,
                pdf_page=unit.pdf_page,
                ordinal=unit.ordinal,
                content_type=unit.content_type.value,
                derived=unit.derived,
                extraction_quality=unit.extraction_quality.value,
                via=via,
                rule_ids=("synthetic.rule.v1",) if via == "expansion" else (),
                exact_terms=(),
                bm25_raw=-1.0 - rank,
                duplicate_evidence_ids=(),
                context=ContextRef(before=(), after=(), section_heading_id=None, parent_heading_id=None),
            )
        )
    # The trace is not read by selection, so it is left out here.
    return RetrievalResult(document_id=DOC, query=query, candidates=tuple(candidates), trace=None)  # type: ignore[arg-type]


def _run(question, members_by_component, units):
    """Analyse ``question`` and select with the retrieval results given per component."""
    analysis = analyze(question)
    retrieved = {}
    for component in analysis.components:
        if component.searchable:
            members = members_by_component[component.component_id]
            retrieved[component.component_id] = _retrieval(component.retrieval_query, members)
    return analysis, select_candidates(analysis, retrieved, units)


def _assert_quotes_are_page_slices(page_text, selection):
    """A quote and its answer span are the page's own text at the page offsets (D49). The page text is the
    hand-written text, never the unit's raw text, so the check can fail."""
    for component in selection.components:
        for candidate in component.candidates:
            assert page_text[candidate.page_start : candidate.page_end] == candidate.quote
            if candidate.answer_span is not None:
                assert candidate.answer_page_start is not None
                assert page_text[candidate.answer_page_start : candidate.answer_page_end] == candidate.answer_span
                assert candidate.answer_span in candidate.quote


def _single(selection):
    assert len(selection.components) == 1
    return selection.components[0]


PAGE_WHAT = "The board approves the loan for small businesses. Staff file reports monthly."


def test_what_gives_the_sentence_that_holds_every_target_and_no_answer_span():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_WHAT, [(0, len(PAGE_WHAT))])
    _, selection = _run(
        "What is the loan for small businesses?",
        {"c1": [(unit, "original")]},
        {unit.evidence_id: unit},
    )
    component = _single(selection)
    assert component.status == ComponentStatus.CANDIDATES
    assert [c.quote for c in component.candidates] == ["The board approves the loan for small businesses."]
    candidate = component.candidates[0]
    assert candidate.rule_id == "what.sentence.v1"
    assert candidate.granularity == "sentence"
    assert candidate.answer_span is None and candidate.answer_kind is None
    assert "no_answer_span" in candidate.flags
    _assert_quotes_are_page_slices(PAGE_WHAT, selection)


PAGE_LIMIT = "The limit for loans is 30 days after approval."


def test_how_many_gives_the_single_value_with_its_unit_as_the_answer_span():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_LIMIT, [(0, len(PAGE_LIMIT))])
    _, selection = _run(
        "How many days is the limit for loans?",
        {"c1": [(unit, "original")]},
        {unit.evidence_id: unit},
    )
    candidate = _single(selection).candidates[0]
    assert candidate.rule_id == "how_many.value_with_unit.v1"
    assert candidate.answer_span == "30 days"
    assert candidate.answer_kind == "number"
    assert candidate.quote == PAGE_LIMIT
    _assert_quotes_are_page_slices(PAGE_LIMIT, selection)


PAGE_TWO_VALUES = "The fee for loans is 5 USD and the limit is 30 days."


def test_how_many_withholds_the_answer_when_two_quantities_are_in_the_sentence():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_TWO_VALUES, [(0, len(PAGE_TWO_VALUES))])
    _, selection = _run(
        "How many days is the limit for loans?",
        {"c1": [(unit, "original")]},
        {unit.evidence_id: unit},
    )
    candidate = _single(selection).candidates[0]
    assert candidate.answer_span is None
    assert "multiple_values" in candidate.flags


PAGE_WHEN = "The loan report is due on 4 March 2024."


def test_when_gives_the_one_date_as_the_answer_span():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_WHEN, [(0, len(PAGE_WHEN))])
    _, selection = _run("When is the loan report due?", {"c1": [(unit, "original")]}, {unit.evidence_id: unit})
    candidate = _single(selection).candidates[0]
    assert candidate.rule_id == "when.date_or_period.v1"
    assert candidate.answer_span == "4 March 2024"
    assert candidate.answer_kind == "date"
    _assert_quotes_are_page_slices(PAGE_WHEN, selection)


PAGE_MUST_NOT = "Staff must not share passwords with visitors."


def test_whether_gives_the_permission_marker_and_its_polarity_as_the_answer_span():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_MUST_NOT, [(0, len(PAGE_MUST_NOT))])
    _, selection = _run(
        "Is it permitted to share passwords?", {"c1": [(unit, "original")]}, {unit.evidence_id: unit}
    )
    candidate = _single(selection).candidates[0]
    assert candidate.rule_id == "whether.permission_marker.v1"
    assert candidate.answer_span == "must not"
    assert candidate.answer_kind == "permission_marker"
    assert candidate.negated is True
    _assert_quotes_are_page_slices(PAGE_MUST_NOT, selection)


def test_whether_without_a_marker_gives_no_candidate_and_says_why():
    page = "Staff share passwords with visitors."
    unit = _unit(1, ContentType.PARAGRAPH, page, [(0, len(page))])
    _, selection = _run("Is it permitted to share passwords?", {"c1": [(unit, "original")]}, {unit.evidence_id: unit})
    component = _single(selection)
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.reasons == ("no sentence with every target term also has a permission or prohibition marker",)


PAGE_CONDITIONS = "The fee is waived for staff. It applies unless the loan is renewed."


def test_conditions_give_the_whole_passage_when_it_holds_a_condition_marker():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_CONDITIONS, [(0, len(PAGE_CONDITIONS))])
    _, selection = _run(
        "Under what conditions is the fee waived for staff?",
        {"c1": [(unit, "original")]},
        {unit.evidence_id: unit},
    )
    candidate = _single(selection).candidates[0]
    assert candidate.rule_id == "conditions.passage.v1"
    assert candidate.granularity == "passage"
    assert candidate.quote == PAGE_CONDITIONS
    _assert_quotes_are_page_slices(PAGE_CONDITIONS, selection)


PAGE_COMPARE = "Gold accounts pay fees monthly. Silver accounts pay no fees."


def test_each_comparison_subject_is_selected_on_its_own():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_COMPARE, [(0, len(PAGE_COMPARE))])
    analysis, selection = _run(
        "Compare the fees of gold and silver accounts.",
        {"c1": [(unit, "original")], "c2": [(unit, "original")]},
        {unit.evidence_id: unit},
    )
    assert [c.component_id for c in selection.components] == ["c1", "c2"]
    assert selection.components[0].candidates[0].quote == "Gold accounts pay fees monthly."
    assert selection.components[1].candidates[0].quote == "Silver accounts pay no fees."
    assert all(c.candidates[0].rule_id == "comparison.subject_sentence.v1" for c in selection.components)
    _assert_quotes_are_page_slices(PAGE_COMPARE, selection)


PAGE_FORMS = "The forms include a loan form and a bank form."


def test_which_flags_a_list_marker_and_gives_no_answer_span():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_FORMS, [(0, len(PAGE_FORMS))])
    _, selection = _run("Which forms are required for the loan?", {"c1": [(unit, "original")]}, {unit.evidence_id: unit})
    candidate = _single(selection).candidates[0]
    assert candidate.answer_span is None
    assert "list_marker" in candidate.flags and "no_answer_span" in candidate.flags


PAGE_CELL = "Loan limit: 30 days"


def test_a_table_cell_is_passage_only_even_when_it_holds_a_value():
    cell = _unit(1, ContentType.TABLE_CELL, PAGE_CELL, [(0, len(PAGE_CELL))])
    _, selection = _run("How many days is the loan limit?", {"c1": [(cell, "original")]}, {cell.evidence_id: cell})
    candidate = _single(selection).candidates[0]
    assert candidate.granularity == "passage"
    assert candidate.quote == PAGE_CELL
    assert candidate.answer_span is None
    assert "table_cell" in candidate.flags and "no_answer_span" in candidate.flags


def test_a_derived_table_row_is_never_quoted_and_is_listed_as_dropped():
    row_page = "Low | 1 | Rare"
    row = _unit(1, ContentType.TABLE_ROW, row_page, [(0, len(row_page))], derived=True)
    _, selection = _run("What is the rating for low?", {"c1": [(row, "original")]}, {row.evidence_id: row})
    component = _single(selection)
    assert component.candidates == ()
    assert [(d.evidence_id, d.reason) for d in component.dropped] == [(row.evidence_id, "derived_row")]
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.reasons == ("every retrieved unit is a generated table row, which is never quoted",)


def test_a_sentence_that_would_join_two_source_spans_is_dropped_with_a_record():
    page = "Fee due\n\nin March"
    cell = _unit(1, ContentType.TABLE_CELL, page, [(0, 7), (9, 17)])
    assert cell.raw_text == "Fee due\nin March"
    _, selection = _run("What is the fee due in March?", {"c1": [(cell, "original")]}, {cell.evidence_id: cell})
    component = _single(selection)
    assert component.candidates == ()
    assert [(d.evidence_id, d.reason) for d in component.dropped] == [(cell.evidence_id, "crosses_source_span")]


def test_a_sentence_inside_one_of_two_spans_maps_to_its_own_page_offsets():
    page = "Cell one.\n\nLoan limit is 30 days. Other text."
    cell = _unit(1, ContentType.PARAGRAPH, page, [(0, 9), (11, len(page))])
    _, selection = _run("How many days is the loan limit?", {"c1": [(cell, "original")]}, {cell.evidence_id: cell})
    candidate = _single(selection).candidates[0]
    assert candidate.quote == "Loan limit is 30 days."
    assert (candidate.page_start, candidate.page_end) == (page.index("Loan"), page.index("Loan") + len(candidate.quote))
    assert candidate.answer_span == "30 days"
    assert (candidate.answer_page_start, candidate.answer_page_end) == (page.index("30 days"), page.index("30 days") + 7)
    _assert_quotes_are_page_slices(page, selection)


def test_a_replacement_character_is_flagged_and_the_candidate_is_kept():
    page = "The nation�s limit is 30 days."
    unit = _unit(1, ContentType.PARAGRAPH, page, [(0, len(page))])
    _, selection = _run("How many days is the nation limit?", {"c1": [(unit, "original")]}, {unit.evidence_id: unit})
    candidate = _single(selection).candidates[0]
    assert "replacement_character" in candidate.flags
    assert candidate.answer_span == "30 days"


def test_a_passage_reached_only_through_a_reviewed_rule_is_expansion_only_and_is_kept_by_reference():
    page = "The board approves the loan for small businesses."
    unit = _unit(1, ContentType.PARAGRAPH, page, [(0, len(page))])
    retrieval = _retrieval("loan small businesses", [(unit, "expansion")])
    analysis = analyze("What is the loan for small businesses?")
    selection = select_candidates(analysis, {"c1": retrieval}, {unit.evidence_id: unit})
    component = _single(selection)
    assert component.status == ComponentStatus.EXPANSION_ONLY
    candidate = component.candidates[0]
    assert candidate.expansion_only is True
    assert candidate.retrieval is retrieval.candidates[0]
    assert "D38" in component.reasons[0]


def test_original_word_passages_outrank_the_status_of_expansion_only_ones():
    first = _unit(1, ContentType.PARAGRAPH, PAGE_WHAT, [(0, len(PAGE_WHAT))])
    second_page = "Small businesses hold the loan for a year."
    second = _unit(2, ContentType.PARAGRAPH, second_page, [(0, len(second_page))], page=2)
    _, selection = _run(
        "What is the loan for small businesses?",
        {"c1": [(first, "original"), (second, "expansion")]},
        {first.evidence_id: first, second.evidence_id: second},
    )
    component = _single(selection)
    assert component.status == ComponentStatus.CANDIDATES
    assert [c.expansion_only for c in component.candidates] == [False, True]


def test_an_unsearchable_component_is_reported_with_its_reason_and_the_others_still_run():
    page = "The loan limit for staff is set by the board."
    unit = _unit(1, ContentType.PARAGRAPH, page, [(0, len(page))])
    analysis, selection = _run(
        "Why is the rule applied? What is the loan limit for staff?",
        {"c2": [(unit, "original")]},
        {unit.evidence_id: unit},
    )
    first, second = selection.components
    assert first.status == ComponentStatus.UNSUPPORTED
    assert first.reasons == ("why questions are not supported",)
    assert first.candidates == () and first.dropped == ()
    assert second.status == ComponentStatus.CANDIDATES
    assert second.candidates[0].quote == page


def test_an_ambiguous_component_is_reported_and_never_searched():
    analysis, selection = _run("What is the maximum amount?", {}, {})
    component = _single(selection)
    assert component.status == ComponentStatus.AMBIGUOUS
    assert component.reasons == ("the question names no subject to search for",)


def test_a_searchable_component_without_a_retrieval_result_is_an_error():
    analysis = analyze("What is the loan for small businesses?")
    with pytest.raises(SelectionError, match="no retrieval result"):
        select_candidates(analysis, {}, {})


def test_a_retrieval_result_for_another_query_is_an_error():
    analysis = analyze("What is the loan for small businesses?")
    wrong = _retrieval("loan", [])
    with pytest.raises(SelectionError, match="answers 'loan'"):
        select_candidates(analysis, {"c1": wrong}, {})


def test_a_retrieved_unit_that_was_not_loaded_is_an_error():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_WHAT, [(0, len(PAGE_WHAT))])
    analysis = analyze("What is the loan for small businesses?")
    with pytest.raises(SelectionError, match="no unit was given"):
        select_candidates(analysis, {"c1": _retrieval(analysis.components[0].retrieval_query, [(unit, "original")])}, {})


def test_no_retrieved_unit_gives_a_reason_that_says_so():
    analysis = analyze("What is the loan for small businesses?")
    selection = select_candidates(analysis, {"c1": _retrieval(analysis.components[0].retrieval_query, [])}, {})
    component = _single(selection)
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.reasons == ("the search returned no unit for this query",)


def test_a_sentence_missing_one_target_term_is_not_a_candidate_and_the_reason_names_the_terms():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_WHAT, [(0, len(PAGE_WHAT))])
    _, selection = _run("What is the loan for remote workers?", {"c1": [(unit, "original")]}, {unit.evidence_id: unit})
    component = _single(selection)
    assert component.candidates == ()
    assert component.reasons == ("no retrieved sentence contains all of: loan, remote, workers",)


def test_values_in_a_quote_carry_offsets_into_that_quote():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_LIMIT, [(0, len(PAGE_LIMIT))])
    _, selection = _run("How many days is the limit for loans?", {"c1": [(unit, "original")]}, {unit.evidence_id: unit})
    candidate = _single(selection).candidates[0]
    assert candidate.values
    for value in candidate.values:
        assert candidate.quote[value.start : value.end] == value.text


def test_selection_is_deterministic_for_the_same_inputs():
    unit = _unit(1, ContentType.PARAGRAPH, PAGE_TWO_VALUES, [(0, len(PAGE_TWO_VALUES))])
    question = "How many days is the limit for loans?"
    _, first = _run(question, {"c1": [(unit, "original")]}, {unit.evidence_id: unit})
    _, second = _run(question, {"c1": [(unit, "original")]}, {unit.evidence_id: unit})
    assert first == second
