"""Shared helpers for the P6 tests: labelled synthetic stored documents and the P4 and P5 pipeline (ARCHITECTURE §15).

No PDF is read here. Each document is hand-built with ``tests.fixtures.retrieval_docs``, so every expected quote and
offset is known. ``flagged_pages`` writes a page with the WARNING status and one stored issue, and its units carry
the same quality, so the page and its units agree.
"""

from __future__ import annotations

from dataclasses import replace

from app.document_structure.models import ContentType
from app.evidence.selection import SelectionResult, select_candidates
from app.ingestion.models import Issue, PageStatus, QualityStatus
from app.question_processing.analysis import QuestionAnalysis, analyze
from app.retrieval.bm25 import search
from app.storage import Store
from tests.fixtures.retrieval_docs import Item, build, filler
from tests.fixtures.store_records import make_page

CREATED = "2026-01-01T00:00:00Z"
ISSUE_CODE = "reading_order_uncertain"


def main_items() -> list[Item]:
    """The main synthetic page: clean sentences, a prohibition, a permission, a qualified sentence, a table cell, a
    two-value sentence and a derived table row. Page 1 only."""
    return [
        Item(page=1, text="The board approves the loan for small businesses."),
        Item(page=1, text="The limit for loans is 30 days after approval."),
        *filler(12, page=1),
        Item(page=1, text="The fee for loans is 5 USD and the limit is 30 days."),
        Item(page=1, text="Staff must not share passwords with visitors."),
        Item(page=1, text="Staff may share the guide with visitors."),
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


def clean_items() -> list[Item]:
    """A page with clean sentences only. Each sentence has a neighbour that holds no qualifier."""
    return [
        Item(page=1, text="The board approves the loan for small businesses."),
        Item(page=1, text="The limit for loans is 30 days after approval."),
        Item(page=1, text="Staff must not share passwords with visitors."),
        Item(page=1, text="Staff may share the guide with visitors."),
        Item(page=1, text="Each loan request is reviewed by the credit office."),
    ]


def stored_document(document_id: str, items: list[Item], *, flagged_pages: tuple[int, ...] = ()) -> Store:
    """Write a synthetic document to a fresh in-memory store. ``flagged_pages`` become WARNING pages."""
    marked = [replace(item, quality=QualityStatus.WARNING) if item.page in flagged_pages else item for item in items]
    extracted, structure = build(document_id, marked)
    if flagged_pages:
        pages = []
        for page in extracted.pages:
            if page.pdf_page in flagged_pages:
                flagged = make_page(page.pdf_page, page.raw_text, status=PageStatus.WARNING)
                page = flagged.model_copy(
                    update={"issues": [Issue(code=ISSUE_CODE, severity="warning", detail="synthetic flag")]}
                )
            pages.append(page)
        extracted = extracted.model_copy(update={"pages": pages})
    store = Store.open(":memory:")
    store.write_document(extracted, structure, created_at=CREATED)
    return store


def selection_for(store: Store, document_id: str, question: str) -> tuple[QuestionAnalysis, SelectionResult]:
    """The P4 search and the P5 selection for one question. The same steps as the P5 integration tests."""
    analysis = analyze(question)
    retrieved = {}
    units = {}
    for component in analysis.components:
        if not component.searchable:
            continue
        result = search(store, document_id, component.retrieval_query, context_window=0)
        retrieved[component.component_id] = result
        for candidate in result.candidates:
            if candidate.evidence_id not in units:
                units[candidate.evidence_id] = store.load_unit(document_id, candidate.evidence_id)
    return analysis, select_candidates(analysis, retrieved, units)


def candidate_quoting(selection: SelectionResult, fragment: str):
    """The first candidate, in any component, whose quote contains ``fragment``. Fails the test when none does."""
    for component in selection.components:
        for candidate in component.candidates:
            if fragment in candidate.quote:
                return candidate
    raise AssertionError(f"no candidate quotes {fragment!r}")
