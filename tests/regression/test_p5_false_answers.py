"""P5 regression set: ways a selection could give a false answer (SPEC §12; D48-D51, D56, D59).

Each case names one way that a value, a marker or a sentence could be taken for an answer it is not. A case is
only meaningful if it can fail, so each one first shows its precondition (a candidate exists, or a stated reason
is given), and then asserts the outcome the rules in ARCHITECTURE §14 require. A future false answer is added here
with its own name (SPEC §12). The sentences are hand-written.
"""

from __future__ import annotations

from app.document_structure.models import ContentType
from app.evidence import ComponentStatus, select_candidates
from app.question_processing import analyze
from app.retrieval.bm25 import ContextRef, RetrievalCandidate, RetrievalResult
from tests.fixtures.store_records import make_unit

DOC = "doc-" + "7" * 16


def _run(question, page_text, *, content_type=ContentType.PARAGRAPH):
    """Analyse ``question``, then select over one unit whose text is ``page_text``."""
    unit = make_unit(DOC, 1, 1, content_type, page_text, [(0, len(page_text))])
    analysis = analyze(question)
    retrieved = {}
    for component in analysis.components:
        if not component.searchable:
            continue
        candidate = RetrievalCandidate(
            rank=1,
            evidence_id=unit.evidence_id,
            pdf_page=1,
            ordinal=1,
            content_type=unit.content_type.value,
            derived=False,
            extraction_quality=unit.extraction_quality.value,
            via="original",
            rule_ids=(),
            exact_terms=(),
            bm25_raw=-1.0,
            duplicate_evidence_ids=(),
            context=ContextRef(before=(), after=(), section_heading_id=None, parent_heading_id=None),
        )
        retrieved[component.component_id] = RetrievalResult(
            document_id=DOC,
            query=component.retrieval_query,
            candidates=(candidate,),
            trace=None,  # type: ignore[arg-type]
        )
    return select_candidates(analysis, retrieved, {unit.evidence_id: unit})


def _only(selection):
    assert len(selection.components) == 1
    return selection.components[0]


def test_a_footnote_numeral_is_not_read_as_a_value_and_the_real_value_is_the_answer():
    component = _only(_run("How many days must agencies comply with FISMA?", "Agencies comply with FISMA,1 within 30 days."))
    assert component.status == ComponentStatus.CANDIDATES  # precondition: the sentence is a candidate
    candidate = component.candidates[0]
    assert candidate.answer_span == "30 days"
    assert "1" not in [value.text for value in candidate.values]


def test_a_dotted_identifier_does_not_satisfy_a_numeric_target():
    # The question asks about 3.5. The sentence has only 3.5.2, a different identifier (D33, D51).
    component = _only(_run("How many days apply under 3.5?", "Section 3.5.2 sets 30 days for review."))
    assert component.candidates == ()
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.reasons == ("no retrieved sentence contains all of: 3.5",)


def test_a_value_split_across_a_line_wrap_keeps_its_break_in_the_answer_and_the_quote():
    component = _only(
        _run("How many days apply to loans after approval?", "Loans need approval within 30\n\ndays of the request.")
    )
    assert component.status == ComponentStatus.CANDIDATES  # precondition
    candidate = component.candidates[0]
    assert candidate.answer_span == "30\n\ndays"
    assert candidate.quote == "Loans need approval within 30\n\ndays of the request."


def test_an_abbreviation_inside_a_name_does_not_split_the_sentence_that_holds_the_answer():
    component = _only(_run("Who approves the loan?", "The U.S. Department approves the loan for each state."))
    assert component.status == ComponentStatus.CANDIDATES  # precondition
    assert component.candidates[0].quote == "The U.S. Department approves the loan for each state."


def test_a_negative_marker_is_reported_as_the_whole_phrase_and_its_polarity_is_kept():
    component = _only(_run("Is it permitted to share passwords?", "Staff must not share passwords."))
    assert component.status == ComponentStatus.CANDIDATES  # precondition
    candidate = component.candidates[0]
    assert candidate.answer_span == "must not"
    assert candidate.negated is True


def test_a_later_clause_with_a_pronoun_and_no_earlier_subject_is_ambiguous_and_is_not_searched():
    # The sentence contains `due`. Without the pronoun rule, that word alone would make it a candidate (D56).
    selection = _run("What is the fee and when is it due?", "The fee is due in March.")
    later = selection.components[1]
    assert later.status == ComponentStatus.AMBIGUOUS
    assert later.reasons == ("a pronoun refers to an earlier subject, but no earlier subject was named",)
    assert later.candidates == ()


def test_a_permission_question_whose_sentence_has_no_marker_gives_no_answer_and_says_why():
    component = _only(_run("Is it permitted to share passwords?", "Staff share passwords with visitors."))
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.reasons == ("no sentence with every target term also has a permission or prohibition marker",)


def test_a_condition_question_whose_passage_has_no_condition_marker_gives_no_answer_and_says_why():
    component = _only(_run("Under what conditions is the fee waived for staff?", "The fee is waived for staff."))
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.reasons == ("no passage with every target term also has a condition marker",)


def test_a_permanent_employee_sentence_is_not_evidence_for_a_contract_employee_question():
    # The spec's own example of an entity mismatch. The sentence has the attribute word and the other words,
    # but not `contract`, so it is not a candidate and the reason names the terms that were required.
    component = _only(
        _run("What is the leave policy for contract employees?", "Permanent employees follow the leave policy monthly.")
    )
    assert component.candidates == ()
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert "contract" in component.reasons[0]


def test_a_section_number_before_a_count_noun_in_a_heading_is_not_a_quantity():
    # Without the capital-letter and dotted-number guards, `3.2 Risk` would read as 3.2 in the unit `risk`.
    component = _only(
        _run(
            "How many risk board assessments are needed?",
            "3.2 Risk board assessments",
            content_type=ContentType.HEADING,
        )
    )
    assert component.status == ComponentStatus.NO_CANDIDATES
    assert component.candidates == ()
    assert component.reasons == (
        "no sentence with every target term also has a number with a unit, a percentage or a currency amount",
    )
