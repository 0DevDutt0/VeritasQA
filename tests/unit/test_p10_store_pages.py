"""P10: the page rows that the ``report`` command reads (ARCHITECTURE §19.2). Read only."""

from __future__ import annotations

from tests.fixtures.retrieval_docs import Item
from tests.fixtures.verification_docs import ISSUE_CODE, main_items, stored_document

DOC = "doc-" + "5" * 16


def test_page_rows_are_in_page_order_and_carry_the_warning_codes_of_flagged_pages():
    items = main_items() + [Item(page=2, text="The board approves the loan for small businesses.")]
    store = stored_document(DOC, items, flagged_pages=(2,))
    try:
        rows = store.page_rows(DOC)
        assert rows, "the synthetic document has pages"
        numbers = [row.pdf_page for row in rows]
        assert numbers == sorted(numbers)
        flagged = [row for row in rows if row.pdf_page == 2]
        assert len(flagged) == 1
        assert flagged[0].status == "WARNING"
        assert ISSUE_CODE in flagged[0].warnings
        for row in rows:
            if row.pdf_page != 2:
                assert row.status != "WARNING"
                assert ISSUE_CODE not in row.warnings
    finally:
        store.close()


def test_page_rows_of_an_unknown_document_are_empty_and_not_an_error():
    store = stored_document(DOC, main_items())
    try:
        assert store.page_rows("doc-" + "0" * 16) == []
    finally:
        store.close()
