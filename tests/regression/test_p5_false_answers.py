"""P5 regression set: ways a selection rule could give a false answer (SPEC §12; D48-D51).

Each case names a way that a value, a marker or a sentence could be taken for an answer it is not. A future
false answer is added here with its own name (SPEC §12: every discovered false answer becomes a regression case).
The sentences are hand-written. The expected result is the one the rule in ARCHITECTURE §14 requires.
"""

from __future__ import annotations

import pytest

from app.document_structure.models import ContentType
from app.evidence import ComponentStatus, select_candidates
from app.question_processing import analyze
from app.retrieval.bm25 import ContextRef, RetrievalCandidate, RetrievalResult
from tests.fixtures.store_records import make_unit

DOC = "doc-" + "7" * 16


def _run(question, page_text, *, content_type=ContentType.PARAGRAPH):
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
            document_id=DOC, query=component.retrieval_query, candidates=(candidate,), trace=None  # type: ignore[arg-type]
        )
    return select_candidates(analysis, retrieved, {unit.evidence_id: unit})


def test_a_footnote_numeral_is_never_the_answer_to_a_how_many_question():
    selection = _run("How many days must agencies comply?", "Agencies must comply with FISMA,1 the rule.")
    component = selection.components[0]
    candidates = component.candidates
    assert all(candidate.answer_span is None for candidate in candidates)


def test_a_dotted_identifier_does_not_satisfy_a_numeric_target():
    # The question asks about 3.5. The sentence has only 3.5.2, which is a different identifier (D33, D51).
    selection = _run("How many days apply under 3.5?", "Section 3.5.2 sets 30 days for review.")
    component = selection.components[0]
    assert component.candidates == ()
    assert component.status == ComponentStatus.NO_CANDIDATES


def test_a_value_split_across_a_line_wrap_is_quoted_verbatim_with_its_break():
    selection = _run(
        "How many days apply to loans after approval?", "Loans need approval within 30\n\ndays of the request."
    )
    candidate = selection.components[0].candidates[0]
    assert candidate.answer_span == "30\n\ndays"
    assert candidate.quote == "Loans need approval within 30\n\ndays of the request."


def test_an_abbreviation_inside_a_name_does_not_split_the_sentence_that_holds_the_answer():
    selection = _run("Who approves the loan?", "The U.S. Department approves the loan for each state.")
    candidate = selection.components[0].candidates[0]
    assert candidate.quote == "The U.S. Department approves the loan for each state."


def test_a_negative_marker_is_never_reported_as_the_bare_word_that_it_contains():
    selection = _run("Is it permitted to share passwords?", "Staff must not share passwords.")
    candidate = selection.components[0].candidates[0]
    assert candidate.answer_span == "must not"
    assert candidate.negated is True


def test_a_clause_with_a_pronoun_and_no_earlier_subject_is_not_searched_on_its_predicate():
    selection = _run("What is the fee and when is it due?", "The fee is due in March.")
    second = selection.components[1]
    assert second.status == ComponentStatus.AMBIGUOUS
    assert second.candidates == ()


@pytest.mark.parametrize(
    "page_text, question",
    [
        ("Staff must not share passwords with visitors.", "Is sharing permitted for staff?"),
        ("The fee is waived for staff.", "Under what conditions is the fee waived for staff?"),
    ],
)
def test_a_passage_that_lacks_the_required_marker_is_never_an_answer(page_text, question):
    selection = _run(question, page_text)
    for candidate in selection.components[0].candidates:
        assert candidate.answer_span is None or candidate.answer_kind == "permission_marker"
