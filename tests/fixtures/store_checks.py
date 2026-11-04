"""Shared checks for the P3 store tests.

``brute_force_phrase`` is the reference for the candidate step: the exact check applied to every body
unit, with no FTS query. A correct search returns exactly the same units, so the FTS step can only
narrow the work, never change the answer.
"""

from __future__ import annotations

from app.retrieval.phrase import span_matches
from app.retrieval.query import build_phrase_query
from app.storage import Store

STORE_TABLES = (
    "documents",
    "pages",
    "sections",
    "evidence_units",
    "source_locations",
    "table_cells",
    "structure_issues",
    "evidence_fts",
    "evaluations",
)


def brute_force_phrase(store: Store, document_id: str, phrase: str) -> list[str]:
    """Evidence IDs of the body units whose verbatim spans pass the exact check, sorted."""
    query = build_phrase_query(phrase)
    structure = store.load_structure(document_id)
    texts = store.page_texts(document_id, {unit.pdf_page for unit in structure.units})
    hits: list[str] = []
    for unit in structure.units:
        if not unit.body_retrieval:
            continue
        page_text = texts[unit.pdf_page]
        if any(span_matches(page_text[start:end], query) for start, end in unit.source_spans):
            hits.append(unit.evidence_id)
    return sorted(hits)


def row_counts(store: Store) -> dict[str, int]:
    """The row count of every table, for proving that a failed or hostile call changed nothing."""
    return {
        table: store._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608 - fixed names
        for table in STORE_TABLES
    }
