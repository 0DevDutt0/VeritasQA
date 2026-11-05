"""A page whose text could not be fully read is named in the warnings, and the status does not change (D123).

The page is marked ``unverified`` in its stored row, which is the only change to the synthetic document. The question is
answered from page 1, so the status and the answer spans must stay the same, and only one warning line must be added.
"""

from __future__ import annotations

from app.decision import DecisionStatus, answer, load_policy
from app.decision.engine import _unread_page_notice
from app.ingestion.models import QualityStatus
from app.storage.store import PageRow
from tests.fixtures.retrieval_docs import Item
from tests.fixtures.verification_docs import main_items, stored_document

DOC = "doc-" + "a" * 16
LIMIT = "How many days is the limit for loans?"
UNREAD_LINE = (
    "Page 2 could not be fully read: the stored text may be incomplete, and images on it are not read. "
    "Nothing on it is accepted as evidence."
)


def _document_with_a_second_page():
    items = main_items() + [Item(page=2, text="The annex lists the offices and their opening hours.")]
    return stored_document(DOC, items)


def _mark_unverified(store, page: int) -> None:
    store._conn.execute(
        "UPDATE pages SET quality_status = ? WHERE document_id = ? AND pdf_page = ?",
        (QualityStatus.UNVERIFIED.value, DOC, page),
    )
    store._conn.commit()


def test_an_unreadable_page_is_named_and_the_answer_does_not_change():
    store = _document_with_a_second_page()
    baseline = answer(store, DOC, LIMIT, load_policy())
    _mark_unverified(store, 2)
    response = answer(store, DOC, LIMIT, load_policy())
    assert baseline.status == DecisionStatus.ANSWERED
    assert response.status == baseline.status
    assert response.answer_spans == baseline.answer_spans
    assert response.warnings == baseline.warnings + (UNREAD_LINE,)
    store.close()


def test_no_notice_is_added_when_every_page_is_readable():
    store = _document_with_a_second_page()
    assert answer(store, DOC, LIMIT, load_policy()).warnings == ()
    store.close()


def test_the_notice_lists_every_unreadable_page_in_order():
    def row(page: int, quality: str) -> PageRow:
        return PageRow(
            pdf_page=page,
            printed_page=None,
            status="OK",
            quality_status=quality,
            extraction_method="native_text",
            warnings=(),
        )

    rows = [row(1, "verified"), row(2, "unverified"), row(39, "unverified")]
    assert _unread_page_notice(rows) == (
        "Pages 2, 39 could not be fully read: the stored text may be incomplete, and images on them are not read. "
        "Nothing on them is accepted as evidence."
    )
    assert _unread_page_notice([row(1, "verified")]) is None
