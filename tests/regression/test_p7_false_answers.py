"""Regression cases for the decision step (SPEC §12: every discovered false answer becomes a case).

Each case has a precondition. The sentence that would be a false answer passes verification on its own, so a decision
step that looked only at that sentence would answer. The same sentence in the document with a contradicting,
qualifying or unverified passage must not be ANSWERED. The expected status is the one ARCHITECTURE §16 gives.
"""

from __future__ import annotations

import pytest

from app.decision import DecisionStatus, answer, load_policy
from app.document_structure.models import ContentType
from app.verification import CheckName, CheckStatus, Verdict, verify
from tests.fixtures.retrieval_docs import Item
from tests.fixtures.verification_docs import candidate_quoting, selection_for, stored_document

DOC = "doc-" + "a" * 16
LIMIT = "How many days is the limit for loans?"
THIRTY = "The limit for loans is 30 days after approval."


def _naive_verdict(question: str, sentence: str) -> Verdict:
    """The verdict of the sentence alone, in a document that holds nothing else (the precondition of each case)."""
    store = stored_document(DOC, [Item(page=1, text=sentence)])
    try:
        analysis, selection = selection_for(store, DOC, question)
        candidate = candidate_quoting(selection, sentence)
        return verify(candidate, analysis, store, DOC).verdict
    finally:
        store.close()


def _status(question: str, items: list[Item], *, flagged_pages: tuple[int, ...] = ()) -> tuple[DecisionStatus, tuple]:
    store = stored_document(DOC, items, flagged_pages=flagged_pages)
    try:
        response = answer(store, DOC, question, load_policy())
        return response.status, response.answer_spans
    finally:
        store.close()


CASES = [
    pytest.param(
        LIMIT,
        THIRTY,
        [Item(page=1, text="The limit for loans for staff is 45 days after approval.")],
        DecisionStatus.AMBIGUOUS_QUERY,
        id="a-value-for-another-scope-next-to-the-answer",
    ),
    pytest.param(
        LIMIT,
        THIRTY,
        [Item(page=1, text="The limit for loans is replaced by 45 days after approval.")],
        DecisionStatus.CONFLICT,
        id="a-stated-replacement-with-another-value",
    ),
    pytest.param(
        LIMIT,
        THIRTY,
        [Item(page=1, text="The limit for loans of 30 days is 45 days after renewal, not 30 days.")],
        DecisionStatus.AMBIGUOUS_QUERY,
        id="a-sentence-that-states-two-values-for-the-subject",
    ),
    pytest.param(
        LIMIT,
        THIRTY,
        [Item(page=1, text="Loans limit: 45 days", content_type=ContentType.TABLE_CELL)],
        DecisionStatus.AMBIGUOUS_QUERY,
        id="a-table-cell-with-another-value",
    ),
    pytest.param(
        LIMIT,
        THIRTY,
        [Item(page=1, text="The limit for loans is 45.")],
        DecisionStatus.AMBIGUOUS_QUERY,
        id="a-bare-number-that-differs-from-the-answer",
    ),
    pytest.param(
        "How much is the limit for loans?",
        "The limit for loans is $5 million.",
        [Item(page=1, text="The limit for loans is $5 billion.")],
        DecisionStatus.CONFLICT,
        id="a-currency-magnitude-that-differs",
    ),
    pytest.param(
        "Is staff permitted to share the guide with visitors?",
        "Staff are permitted to share the guide with visitors.",
        [Item(page=1, text="Staff must not share the guide with visitors.")],
        DecisionStatus.CONFLICT,
        id="a-prohibition-for-the-same-subject",
    ),
]


@pytest.mark.parametrize("question, sentence, extra, expected", CASES)
def test_a_contradicting_passage_stops_the_answer(question, sentence, extra, expected):
    assert _naive_verdict(question, sentence) == Verdict.PASS, "precondition: the sentence passes on its own"
    status, spans = _status(question, [Item(page=1, text=sentence), *extra])
    assert status == expected
    assert spans == ()


def test_the_same_sentence_on_a_flagged_page_is_not_answered():
    assert _naive_verdict(LIMIT, THIRTY) == Verdict.PASS, "precondition: the sentence passes on a verified page"
    status, spans = _status(LIMIT, [Item(page=1, text=THIRTY)], flagged_pages=(1,))
    assert status == DecisionStatus.SOURCE_UNVERIFIED
    assert spans == ()


def test_a_supersession_sentence_without_a_value_neither_answers_nor_blocks():
    assert _naive_verdict(LIMIT, THIRTY) == Verdict.PASS
    status, spans = _status(
        LIMIT,
        [Item(page=1, text="This publication supersedes the limit for loans in earlier editions."), Item(page=1, text=THIRTY)],
    )
    assert status == DecisionStatus.ANSWERED
    assert [span.text for span in spans] == ["30 days"]


def test_an_unverified_check_is_not_turned_into_support_by_a_matching_word():
    # The property word "permitted" is required (D67). A passage that says only "may" must not pass, so no answer.
    sentence = "Staff may share the guide with visitors."
    question = "Is staff permitted to share the guide with visitors?"
    assert _naive_verdict(question, sentence) != Verdict.PASS
    status, spans = _status(question, [Item(page=1, text=sentence)])
    assert status != DecisionStatus.ANSWERED
    assert spans == ()


def test_the_precondition_helper_reports_the_check_that_failed():
    store = stored_document(DOC, [Item(page=1, text="Staff may share the guide with visitors.")])
    try:
        analysis, selection = selection_for(store, DOC, "Is staff permitted to share the guide with visitors?")
        candidate = candidate_quoting(selection, "Staff may share the guide with visitors.")
        report = verify(candidate, analysis, store, DOC)
        assert report.check(CheckName.ATTRIBUTE).status == CheckStatus.UNRESOLVED
    finally:
        store.close()


def test_a_flagged_passage_that_contradicts_a_verified_answer_stops_the_answer():
    # The verified sentence passes on its own. The contradicting sentence sits on a flagged page, so it is a source
    # problem (SPEC §9 SOURCE_UNVERIFIED), and the answer must not be shown as ANSWERED beside it.
    sentence_45 = "The limit for loans is 45 days after approval."
    assert _naive_verdict(LIMIT, THIRTY) == Verdict.PASS, "precondition: the verified sentence passes on its own"
    status, spans = _status(LIMIT, [Item(page=1, text=THIRTY), Item(page=2, text=sentence_45)], flagged_pages=(2,))
    assert status == DecisionStatus.SOURCE_UNVERIFIED
    assert spans == ()


def test_a_flagged_bare_number_that_contradicts_a_verified_answer_is_found_by_the_screen():
    # The contradicting sentence gives its value as a bare number, so it is not an answer candidate (it has no unit). Only
    # the conflict screen compares it. Its page is flagged, so the difference is a source problem, and the answer stops.
    contradicting = "The limit for loans is 45 after approval."
    assert _naive_verdict(LIMIT, THIRTY) == Verdict.PASS, "precondition: the verified sentence passes on its own"
    store = stored_document(DOC, [Item(page=1, text=THIRTY), Item(page=2, text=contradicting)], flagged_pages=(2,))
    try:
        response = answer(store, DOC, LIMIT, load_policy())
    finally:
        store.close()
    assert response.status == DecisionStatus.SOURCE_UNVERIFIED
    assert response.answer_spans == ()
    assert [finding.impact.value for finding in response.conflicts] == ["source"]
