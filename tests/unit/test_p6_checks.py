"""One test per SPEC §7 check (ARCHITECTURE §15). Each test runs the real P4 and P5 steps on a labelled synthetic
document, and then tests the check on the candidate or on a copy of it with one field changed.

A candidate is a claim, so a changed copy must FAIL the check that reads that field. A copy whose field is unchanged
must PASS, which is the precondition that makes each FAIL meaningful.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.question_processing.analysis import analyze
from app.verification import CheckName, CheckStatus, verify
from tests.fixtures.retrieval_docs import Item
from tests.fixtures.verification_docs import (
    ISSUE_CODE,
    candidate_quoting,
    clean_items,
    main_items,
    selection_for,
    stored_document,
)

DOC = "doc-" + "7" * 16
LIMIT_Q = "How many days is the limit for loans?"
LIMIT_FRAGMENT = "The limit for loans is 30 days after approval."


@pytest.fixture(scope="module")
def main():
    store = stored_document(DOC, main_items())
    yield store
    store.close()


@pytest.fixture(scope="module")
def limit(main):
    analysis, selection = selection_for(main, DOC, LIMIT_Q)
    return analysis, candidate_quoting(selection, LIMIT_FRAGMENT)


def _status(report, name: CheckName) -> CheckStatus:
    return report.check(name).status


def test_the_unchanged_candidate_passes_the_quotation_check(main, limit):
    analysis, candidate = limit
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.QUOTATION) == CheckStatus.PASS


def test_a_quote_that_differs_from_the_stored_text_fails_the_quotation_check(main, limit):
    analysis, candidate = limit
    changed = replace(candidate, quote=candidate.quote + "!")
    report = verify(changed, analysis, main, DOC)
    assert _status(report, CheckName.QUOTATION) == CheckStatus.FAIL
    assert "not the stored page text" in report.check(CheckName.QUOTATION).reason


def test_an_empty_quote_fails_the_quotation_check(main, limit):
    analysis, candidate = limit
    report = verify(replace(candidate, quote=""), analysis, main, DOC)
    assert _status(report, CheckName.QUOTATION) == CheckStatus.FAIL


def test_offsets_outside_the_page_fail_the_quotation_check(main, limit):
    analysis, candidate = limit
    report = verify(replace(candidate, page_end=10**6), analysis, main, DOC)
    assert _status(report, CheckName.QUOTATION) == CheckStatus.FAIL


def test_a_candidate_for_a_page_with_no_stored_text_fails_the_quotation_check(main, limit):
    analysis, candidate = limit
    report = verify(replace(candidate, pdf_page=9), analysis, main, DOC)
    assert _status(report, CheckName.QUOTATION) == CheckStatus.FAIL
    assert _status(report, CheckName.LOCATION) == CheckStatus.FAIL


def test_the_unchanged_candidate_passes_the_location_check(main, limit):
    analysis, candidate = limit
    assert _status(verify(candidate, analysis, main, DOC), CheckName.LOCATION) == CheckStatus.PASS


def test_a_unit_that_the_store_does_not_hold_fails_the_location_check(main, limit):
    analysis, candidate = limit
    missing = replace(candidate, retrieval=replace(candidate.retrieval, evidence_id="doc-x:p9999:u0001"))
    report = verify(missing, analysis, main, DOC)
    assert _status(report, CheckName.LOCATION) == CheckStatus.FAIL
    assert "holds no unit" in report.check(CheckName.LOCATION).reason


def test_a_wrong_page_section_rule_or_position_fails_the_location_check(main, limit):
    analysis, candidate = limit
    wrong_section = replace(candidate, section_id="doc-x:s9999")
    wrong_rule = replace(candidate, rule_id="what.sentence.v1")
    wrong_position = replace(candidate, retrieval=replace(candidate.retrieval, ordinal=candidate.retrieval.ordinal + 1))
    for changed in (wrong_section, wrong_rule, wrong_position):
        assert _status(verify(changed, analysis, main, DOC), CheckName.LOCATION) == CheckStatus.FAIL


def test_a_derived_table_row_is_never_quoted(main, limit):
    analysis, candidate = limit
    structure = main.load_structure(DOC)
    row = next(unit for unit in structure.units if unit.derived)
    page_text = main.page_texts(DOC, [row.pdf_page])[row.pdf_page]
    start, end = row.source_spans[0]
    as_row = replace(
        candidate,
        retrieval=replace(
            candidate.retrieval,
            evidence_id=row.evidence_id,
            ordinal=row.ordinal,
            derived=True,
            extraction_quality=row.extraction_quality.value,
        ),
        pdf_page=row.pdf_page,
        section_id=row.section_id,
        quote=page_text[start:end],
        page_start=start,
        page_end=end,
        answer_span=None,
        answer_page_start=None,
        answer_page_end=None,
        answer_kind=None,
    )
    report = verify(as_row, analysis, main, DOC)
    assert _status(report, CheckName.LOCATION) == CheckStatus.FAIL
    assert "never quoted" in report.check(CheckName.LOCATION).reason
    assert report.verdict.value == "FAIL"


def test_the_unchanged_answer_span_passes(main, limit):
    analysis, candidate = limit
    assert candidate.answer_span == "30 days"
    assert _status(verify(candidate, analysis, main, DOC), CheckName.ANSWER_SPAN) == CheckStatus.PASS


def test_a_span_whose_text_or_kind_is_changed_fails_the_answer_span_check(main, limit):
    analysis, candidate = limit
    wrong_text = replace(candidate, answer_span="31 days")
    wrong_kind = replace(candidate, answer_kind="date")
    for changed in (wrong_text, wrong_kind):
        assert _status(verify(changed, analysis, main, DOC), CheckName.ANSWER_SPAN) == CheckStatus.FAIL


def test_an_answer_span_on_a_passage_only_type_fails_the_answer_span_check(main):
    analysis, selection = selection_for(main, DOC, "What is the limit for loans?")
    candidate = candidate_quoting(selection, LIMIT_FRAGMENT)
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.ANSWER_SPAN) == CheckStatus.UNRESOLVED
    assert "passage only" in report.check(CheckName.ANSWER_SPAN).reason
    forged = replace(candidate, answer_span="30 days", answer_page_start=candidate.page_start + 10)
    assert _status(verify(forged, analysis, main, DOC), CheckName.ANSWER_SPAN) == CheckStatus.FAIL


def test_a_passage_with_two_values_has_no_single_span(main):
    analysis, selection = selection_for(main, DOC, LIMIT_Q)
    candidate = candidate_quoting(selection, "The fee for loans is 5 USD")
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.ANSWER_SPAN) == CheckStatus.UNRESOLVED
    assert "more than one value" in report.check(CheckName.ANSWER_SPAN).reason
    assert report.verdict.value == "UNRESOLVED"


def test_the_target_words_pass_the_entity_check(main, limit):
    analysis, candidate = limit
    assert _status(verify(candidate, analysis, main, DOC), CheckName.ENTITY) == CheckStatus.PASS


def test_a_question_about_another_subject_fails_the_entity_check(main, limit):
    _, candidate = limit
    other = analyze("How many days is the guarantee for loans?")
    assert other.components[0].target_terms == ("guarantee", "loans")
    report = verify(candidate, other, main, DOC)
    assert _status(report, CheckName.ENTITY) == CheckStatus.FAIL
    assert "guarantee" in report.check(CheckName.ENTITY).reason


def test_a_property_word_that_is_absent_is_unresolved_not_failed(main):
    analysis, selection = selection_for(main, DOC, "What is the fee for loans?")
    candidate = candidate_quoting(selection, LIMIT_FRAGMENT)
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.ATTRIBUTE) == CheckStatus.UNRESOLVED
    assert "synonyms are not used" in report.check(CheckName.ATTRIBUTE).reason


def test_a_property_word_that_is_present_passes_the_attribute_check(main):
    analysis, selection = selection_for(main, DOC, "What is the fee for loans?")
    candidate = candidate_quoting(selection, "The fee for loans is 5 USD")
    assert _status(verify(candidate, analysis, main, DOC), CheckName.ATTRIBUTE) == CheckStatus.PASS


def test_the_attribute_check_is_not_applicable_without_a_property_word(main):
    analysis = analyze("Who approves the loan?")
    assert analysis.components[0].attribute_terms == ()
    _, selection = selection_for(main, DOC, "Who approves the loan?")
    candidate = candidate_quoting(selection, "The board approves the loan")
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.ATTRIBUTE) == CheckStatus.NOT_APPLICABLE


def test_a_question_value_absent_from_the_passage_is_unresolved(main, limit):
    _, candidate = limit
    analysis = analyze("How many days is the limit of 3.5 for loans?")
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.VALUE) == CheckStatus.UNRESOLVED
    assert "3.5" in report.check(CheckName.VALUE).reason


def test_a_question_without_a_value_makes_the_value_check_not_applicable(main, limit):
    analysis, candidate = limit
    assert _status(verify(candidate, analysis, main, DOC), CheckName.VALUE) == CheckStatus.NOT_APPLICABLE


def test_a_value_present_only_with_a_minus_sign_fails_the_value_check(main, limit):
    _, candidate = limit
    analysis = analyze("How many days is the limit of 3.5 for loans?")
    signed = replace(candidate, quote="The limit for loans is -3.5 days after approval.")
    report = verify(signed, analysis, main, DOC)
    assert _status(report, CheckName.VALUE) == CheckStatus.FAIL


def test_a_neighbour_that_qualifies_the_passage_makes_the_context_check_unresolved(main):
    analysis, selection = selection_for(main, DOC, "Is staff permitted to share the guide with visitors?")
    candidate = candidate_quoting(selection, "Staff may share the guide")
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.CONTEXT) == CheckStatus.UNRESOLVED
    assert "unless" in report.check(CheckName.CONTEXT).reason


def test_a_passage_with_clean_neighbours_passes_the_context_check(main, limit):
    analysis, candidate = limit
    assert _status(verify(candidate, analysis, main, DOC), CheckName.CONTEXT) == CheckStatus.PASS


def test_a_prohibition_keeps_its_polarity_and_passes_the_negation_check(main):
    analysis, selection = selection_for(main, DOC, "Is staff permitted to share passwords with visitors?")
    candidate = candidate_quoting(selection, "Staff must not share passwords")
    assert candidate.negated is True
    assert _status(verify(candidate, analysis, main, DOC), CheckName.NEGATION) == CheckStatus.PASS


def test_a_permission_passes_the_negation_check_with_its_polarity(main):
    analysis, selection = selection_for(main, DOC, "Is staff permitted to share the guide with visitors?")
    candidate = candidate_quoting(selection, "Staff may share the guide")
    assert candidate.negated is False
    assert _status(verify(candidate, analysis, main, DOC), CheckName.NEGATION) == CheckStatus.PASS


def test_a_stored_polarity_that_drops_the_not_fails_the_negation_check(main):
    analysis, selection = selection_for(main, DOC, "Is staff permitted to share passwords with visitors?")
    candidate = candidate_quoting(selection, "Staff must not share passwords")
    report = verify(replace(candidate, negated=False), analysis, main, DOC)
    assert _status(report, CheckName.NEGATION) == CheckStatus.FAIL
    assert "polarity" in report.check(CheckName.NEGATION).reason


def test_a_negated_question_is_unresolved_for_the_negation_check(main):
    analysis, selection = selection_for(main, DOC, "Must staff not share passwords with visitors?")
    candidate = candidate_quoting(selection, "Staff must not share passwords")
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.NEGATION) == CheckStatus.UNRESOLVED
    assert "negated" in report.check(CheckName.NEGATION).reason


def test_a_condition_in_the_passage_makes_the_condition_check_unresolved():
    conditional_doc = "doc-" + "8" * 16
    items = [*clean_items(), Item(page=1, text="Staff may share the guide with visitors if they are trained.")]
    store = stored_document(conditional_doc, items)
    try:
        analysis, selection = selection_for(store, conditional_doc, "Is staff permitted to share the guide with visitors?")
        candidate = candidate_quoting(selection, "if they are trained")
        report = verify(candidate, analysis, store, conditional_doc)
        assert _status(report, CheckName.CONDITION) == CheckStatus.UNRESOLVED
        assert "if" in report.check(CheckName.CONDITION).reason
    finally:
        store.close()


def test_a_flagged_page_fails_the_source_quality_check_as_unresolved_and_names_its_issue():
    store = stored_document(DOC, main_items(), flagged_pages=(1,))
    try:
        analysis, selection = selection_for(store, DOC, LIMIT_Q)
        candidate = candidate_quoting(selection, LIMIT_FRAGMENT)
        report = verify(candidate, analysis, store, DOC)
        assert _status(report, CheckName.SOURCE_QUALITY) == CheckStatus.UNRESOLVED
        assert ISSUE_CODE in report.check(CheckName.SOURCE_QUALITY).reason
        assert _status(report, CheckName.CONTEXT) == CheckStatus.UNRESOLVED
        assert report.verdict.value == "UNRESOLVED"
    finally:
        store.close()


def test_a_flagged_page_is_not_read_for_context_even_when_its_next_unit_is_clean():
    # The candidate is the last unit of a flagged page 1, and its next unit is on a clean page 2. Its own page's order
    # is not verified, so the context check must not read across into the clean page (D62).
    items = [
        Item(page=1, text="The limit for loans is 30 days after approval."),
        Item(page=2, text="Staff may share the guide with visitors."),
    ]
    store = stored_document(DOC, items, flagged_pages=(1,))
    try:
        analysis, selection = selection_for(store, DOC, LIMIT_Q)
        candidate = candidate_quoting(selection, LIMIT_FRAGMENT)
        unit = store.load_unit(DOC, candidate.evidence_id)
        assert unit.next_id is not None and store.load_unit(DOC, unit.next_id).pdf_page == 2
        report = verify(candidate, analysis, store, DOC)
        assert _status(report, CheckName.CONTEXT) == CheckStatus.UNRESOLVED
        assert "not verified" in report.check(CheckName.CONTEXT).reason
    finally:
        store.close()


def test_a_verified_page_passes_the_source_quality_check(main, limit):
    analysis, candidate = limit
    assert _status(verify(candidate, analysis, main, DOC), CheckName.SOURCE_QUALITY) == CheckStatus.PASS


@pytest.mark.parametrize(
    "fragment, flag_text",
    [
        ("The fee for loans is 5 USD", "more than one value"),
        ("Loans limit: 30 days", "table cell is passage only"),
    ],
)
def test_each_blocking_p5_flag_makes_the_flag_check_unresolved(main, fragment, flag_text):
    analysis, selection = selection_for(main, DOC, LIMIT_Q)
    candidate = candidate_quoting(selection, fragment)
    report = verify(candidate, analysis, main, DOC)
    assert _status(report, CheckName.CANDIDATE_FLAGS) == CheckStatus.UNRESOLVED
    assert flag_text in report.check(CheckName.CANDIDATE_FLAGS).reason


def test_an_unknown_flag_makes_the_flag_check_unresolved(main, limit):
    analysis, candidate = limit
    report = verify(replace(candidate, flags=("invented_flag",)), analysis, main, DOC)
    assert _status(report, CheckName.CANDIDATE_FLAGS) == CheckStatus.UNRESOLVED
    assert "unknown flag 'invented_flag'" in report.check(CheckName.CANDIDATE_FLAGS).reason


def test_a_candidate_with_no_flag_passes_the_flag_check(main, limit):
    analysis, candidate = limit
    assert candidate.flags == ()
    assert _status(verify(candidate, analysis, main, DOC), CheckName.CANDIDATE_FLAGS) == CheckStatus.PASS


def test_an_expansion_only_candidate_fails_entity_value_negation_and_condition(main, limit):
    analysis, candidate = limit
    expanded = replace(candidate, retrieval=replace(candidate.retrieval, via="expansion"))
    assert expanded.expansion_only
    report = verify(expanded, analysis, main, DOC)
    for name in (CheckName.ENTITY, CheckName.VALUE, CheckName.NEGATION, CheckName.CONDITION):
        assert _status(report, name) == CheckStatus.FAIL, name
        assert "D38" in report.check(name).reason
    assert report.verdict.value == "FAIL"
