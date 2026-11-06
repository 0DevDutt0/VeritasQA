"""P14 end to end on labelled synthetic documents (ARCHITECTURE §14 'Sentence pairs', §16.2; D133).

Each document is hand-built, so the expected status, answer and passage are known in advance. One item is one unit, so
a pair of sentences in one item is a pair inside one unit, which is the only reach the rule has.
"""

from __future__ import annotations

from app.decision import DecisionStatus, answer, load_policy
from tests.fixtures.retrieval_docs import Item, filler
from tests.fixtures.verification_docs import stored_document

DOC = "doc-" + "c" * 16
TARGET = "The Bluetooth security guide is listed in the catalogue."
UPDATES = "Updates are included as of January 19, 2022."
WHEN_QUESTION = "When were the updates to the Bluetooth security guide included?"

FEE_PAIR = "The course fee is paid in advance. It is due after 30 days."
FEE_SINGLE = "The course fee is due after 45 days."
FEE_QUESTION = "How many days is the course fee due?"


def _answer(store, question):
    return answer(store, DOC, question, load_policy())


def test_a_neighbouring_sentence_answers_a_when_question_end_to_end():
    store = stored_document(DOC, [Item(page=1, text=f"{TARGET} {UPDATES}"), *filler(12, page=1)])
    try:
        response = _answer(store, WHEN_QUESTION)
        assert response.status == DecisionStatus.ANSWERED
        assert [span.text for span in response.answer_spans] == ["January 19, 2022"]
        assert response.conflicts == ()
    finally:
        store.close()


def test_a_neighbour_value_that_differs_from_a_passage_elsewhere_is_screened_and_not_answered():
    store = stored_document(
        DOC,
        [Item(page=1, text=FEE_PAIR), Item(page=1, text=FEE_SINGLE), *filler(12, page=1)],
    )
    try:
        response = _answer(store, FEE_QUESTION)
        assert response.status != DecisionStatus.ANSWERED
        assert any(FEE_PAIR in (finding.first_quote, finding.second_quote) for finding in response.conflicts)
    finally:
        store.close()
