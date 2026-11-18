"""Regression checks for the deterministic clause path through the public answer API."""

import pymupdf
import pytest

from app.decision import DecisionStatus, answer
from app.document_structure import build_structure
from app.ingestion.extract import extract_document
from app.retrieval.config import load_retrieval_config
from app.storage import Store
from tests.fixtures.retrieval_docs import Item
from tests.fixtures.verification_docs import stored_document

DOC = "doc-" + "a" * 16


@pytest.mark.parametrize(
    ("question", "source", "expected"),
    [
        (
            "Where are the audit procedures published?",
            "The audit procedures are published in the staff portal.",
            "the staff portal",
        ),
        (
            "How many reviewers does the policy specify?",
            "The policy specifies at least three qualified reviewers.",
            "at least three",
        ),
        ("By when is the archive review expected?", "The archive review is expected no later than 2029.", "2029"),
        (
            "How is the backup drive protected?",
            "The backup drive is securely protected by encryption.",
            "securely protected by encryption",
        ),
        (
            "Under control OPS.LG-07, how are inspection logs treated?",
            "• Logs are classified by source\n\no OPS.LG-06: Event logs are encrypted\n\no OPS.LG-07: Inspection logs are retained",
            "retained",
        ),
        (
            "May rising humidity affect sensor accuracy?",
            "Rising humidity may affect sensor accuracy.",
            "may affect sensor accuracy",
        ),
    ],
)
def test_answers_carry_the_exact_span_and_page(question, source, expected):
    with stored_document(DOC, [Item(page=1, text=source)]) as store:
        response = answer(store, DOC, question)
        assert response.status == DecisionStatus.ANSWERED
        (span,) = response.answer_spans
        assert span.text == expected
        assert store.page_texts(DOC, [span.pdf_page])[span.pdf_page][span.start : span.end] == expected
        assert any(entry.accepted and entry.verdict == "PASS" for entry in response.verification)
        assert any(entry.via == "extractive" for entry in response.retrieval[0].entries)


@pytest.mark.parametrize(
    ("question", "source"),
    [
        (
            "Where are the emergency audit procedures published?",
            "The audit procedures are published in the staff portal.",
        ),
        ("How should control be applied to a warehouse?", "A control may be applied to a warehouse where practical."),
        (
            "How should control be applied to a warehouse?",
            "Some controls are applicable to warehouses as written, while others need review by checking the following:",
        ),
        ("How many reviewers does the policy specify?", "For example, the policy may specify five reviewers."),
        (
            "How many reviewers does the policy specify?",
            "The policy specifies five reviewers if the appeal is urgent.",
        ),
        ("How many reviewers are required by OPS.LG-08?", "OPS.LG-07: Four reviewers are required."),
    ],
)
def test_an_unresolved_scope_or_condition_does_not_become_an_answer(question, source):
    with stored_document(DOC, [Item(page=1, text=source)]) as store:
        assert not answer(store, DOC, question).answer_spans


def test_conflicting_written_counts_block_the_answer():
    items = [
        Item(page=1, text="The service handbook specifies five support channels."),
        Item(page=2, text="The service handbook lists seven support channels."),
    ]
    with stored_document(DOC, items) as store:
        config = load_retrieval_config().model_copy(update={"k": 1, "expansion_k": 0})
        response = answer(
            store, DOC, "How many support channels does the service handbook define?", retrieval_config=config
        )
    assert response.status == DecisionStatus.AMBIGUOUS_QUERY
    assert response.answer_spans == ()
    assert {item.pdf_page for item in response.evidence} == {1, 2}


def test_a_method_question_keeps_the_state_of_the_object():
    items = [
        Item(page=1, text="Technicians should protect logs with an authenticated channel during transmission."),
        Item(page=1, text="Technicians must store logs in a form that prevents tampering."),
    ]
    question = "How must technicians protect saved logs so that an intruder cannot modify them?"
    with stored_document(DOC, items) as store:
        result = answer(store, DOC, question)
    assert [span.text for span in result.answer_spans] == ["in a form that prevents tampering"]


def test_a_matching_clause_on_unverified_source_is_never_an_answer():
    sentence = "The audit procedures are published in the staff portal."
    with stored_document(DOC, [Item(page=1, text=sentence)], flagged_pages=(1,)) as store:
        result = answer(store, DOC, "Where are the audit procedures published?")
    assert not result.answer_spans


def test_a_named_table_selects_the_matching_row_and_column(tmp_path):
    path = tmp_path / "access-table.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 100), "Table 4. Account access periods")
        rows = (("Policy", "Admin", "Member"), ("Access period", "30 days", "14 days"))
        for row in range(len(rows) + 1):
            y = 120 + 30 * row
            page.draw_line((72, y), (462, y))
        for column in range(len(rows[0]) + 1):
            x = 72 + 130 * column
            page.draw_line((x, 120), (x, 180))
        for row, cells in enumerate(rows):
            for column, text in enumerate(cells):
                page.insert_text((80 + 130 * column, 140 + 30 * row), text)
        document.save(path)
    extracted = extract_document(path, out_root=tmp_path / "extracted")
    with Store.open() as store:
        store.write_document(extracted, build_structure(extracted, path))
        query = "According to Table 4, how long is the admin access period?"
        result = answer(store, extracted.document_id, query)
        assert [span.text for span in result.answer_spans] == ["30 days"]
        assert not answer(store, extracted.document_id, query.replace("Table 4", "Table 5")).answer_spans
