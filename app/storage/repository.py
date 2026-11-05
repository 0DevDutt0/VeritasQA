"""Parameterized SQL for one document at a time (ARCHITECTURE §6).

Every statement binds its values with ``?`` placeholders. The only text that is not bound is a
fixed table or column list. Reads are scoped by ``document_id``, and FTS rows are written only for
units with ``body_retrieval`` set.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from app.common.errors import StorageIntegrityError
from app.document_structure.models import (
    ContentType,
    DocumentStructure,
    EvidenceUnit,
    Section,
    StructureIssue,
    TableCell,
)
from app.ingestion.models import ExtractedDocument, QualityStatus

_DELETE_STATEMENTS: tuple[str, ...] = (
    "DELETE FROM structure_issues WHERE document_id = ?",
    "DELETE FROM table_cells WHERE evidence_id IN (SELECT evidence_id FROM evidence_units WHERE document_id = ?)",
    "DELETE FROM source_locations WHERE document_id = ?",
    "DELETE FROM evidence_fts WHERE document_id = ?",
    "DELETE FROM evidence_units WHERE document_id = ?",
    "DELETE FROM sections WHERE document_id = ?",
    "DELETE FROM pages WHERE document_id = ?",
    "DELETE FROM documents WHERE document_id = ?",
)

_UNIT_COLUMNS = (
    "evidence_id",
    "document_id",
    "pdf_page",
    "printed_page",
    "ordinal",
    "content_type",
    "raw_text",
    "index_text",
    "heading_text",
    "section_id",
    "parent_id",
    "prev_id",
    "next_id",
    "extraction_quality",
    "body_retrieval",
    "derived",
    "table_id",
    "row_index",
    "col_index",
    "row_header",
    "col_header",
    "caption",
    "x0",
    "y0",
    "x1",
    "y1",
)

# Longest list of page numbers bound in one statement. SQLite's limit is far higher; this keeps the
# statements well inside the default parameter budget of older builds.
_PAGE_CHUNK = 400


def _marks(count: int) -> str:
    return ", ".join("?" for _ in range(count))


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _chunks(values: Sequence[int], size: int) -> Iterator[Sequence[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


# ----------------------------------------------------------------------------- writes


def delete_document(conn: sqlite3.Connection, document_id: str) -> None:
    """Remove every row of one document. Other documents are not touched."""
    for statement in _DELETE_STATEMENTS:
        conn.execute(statement, (document_id,))


def insert_document(
    conn: sqlite3.Connection,
    extracted: ExtractedDocument,
    structure: DocumentStructure,
    created_at: str,
) -> None:
    conn.execute(
        "INSERT INTO documents (document_id, source_name, sha256, size_bytes, page_count, "
        "extractor_version, structure_version, pymupdf_version, pdfplumber_version, "
        "extraction_config_sha256, structure_config_sha256, issues_json, created_at) "
        f"VALUES ({_marks(13)})",
        (
            extracted.document_id,
            extracted.source_name,
            extracted.sha256,
            extracted.size_bytes,
            extracted.page_count,
            extracted.extractor_version,
            structure.structure_version,
            extracted.pymupdf_version,
            extracted.pdfplumber_version,
            extracted.config_sha256,
            structure.config_sha256,
            _json([issue.model_dump() for issue in extracted.issues]),
            created_at,
        ),
    )


def insert_pages(conn: sqlite3.Connection, extracted: ExtractedDocument) -> None:
    conn.executemany(
        "INSERT INTO pages (document_id, pdf_page, printed_page, width, height, rotation, status, "
        "quality_status, extraction_method, warnings_json, raw_text, raw_text_sha256) "
        f"VALUES ({_marks(12)})",
        [
            (
                extracted.document_id,
                page.pdf_page,
                page.printed_page,
                page.width,
                page.height,
                page.rotation,
                page.status.value,
                page.quality_status.value,
                page.extraction_method.value,
                _json([issue.model_dump() for issue in page.issues]),
                page.raw_text,
                page.raw_text_sha256,
            )
            for page in extracted.pages
        ],
    )


def insert_sections(conn: sqlite3.Connection, structure: DocumentStructure) -> None:
    conn.executemany(
        "INSERT INTO sections (section_id, document_id, position, level, title, parent_section_id, "
        f"start_pdf_page, heading_id) VALUES ({_marks(8)})",
        [
            (
                section.section_id,
                section.document_id,
                position,
                section.level,
                section.title,
                section.parent_section_id,
                section.start_pdf_page,
                section.heading_id,
            )
            for position, section in enumerate(structure.sections)
        ],
    )


def _unit_row(unit: EvidenceUnit) -> tuple[Any, ...]:
    x0, y0, x1, y1 = unit.bbox
    return (
        unit.evidence_id,
        unit.document_id,
        unit.pdf_page,
        unit.printed_page,
        unit.ordinal,
        unit.content_type.value,
        unit.raw_text,
        unit.index_text,
        unit.heading_text,
        unit.section_id,
        unit.parent_id,
        unit.prev_id,
        unit.next_id,
        unit.extraction_quality.value,
        int(unit.body_retrieval),
        int(unit.derived),
        unit.table_id,
        unit.row_index,
        unit.col_index,
        unit.row_header,
        unit.col_header,
        unit.caption,
        x0,
        y0,
        x1,
        y1,
    )


def insert_units(conn: sqlite3.Connection, structure: DocumentStructure) -> None:
    columns = ", ".join(_UNIT_COLUMNS)
    conn.executemany(
        f"INSERT INTO evidence_units ({columns}) VALUES ({_marks(len(_UNIT_COLUMNS))})",
        [_unit_row(unit) for unit in structure.units],
    )


def insert_locations(conn: sqlite3.Connection, structure: DocumentStructure) -> None:
    """One row per span, so a multi-span unit (a table row or cell) has one row for each of its spans."""
    conn.executemany(
        "INSERT INTO source_locations (document_id, evidence_id, span_index, pdf_page, source_start, source_end) "
        f"VALUES ({_marks(6)})",
        [
            (unit.document_id, unit.evidence_id, index, unit.pdf_page, start, end)
            for unit in structure.units
            for index, (start, end) in enumerate(unit.source_spans)
        ],
    )


def insert_table_cells(conn: sqlite3.Connection, structure: DocumentStructure) -> None:
    conn.executemany(
        "INSERT INTO table_cells (evidence_id, table_id, row_index, col_index, row_header, col_header, caption) "
        f"VALUES ({_marks(7)})",
        [
            (
                record.evidence_id,
                record.table_id,
                record.row_index,
                record.col_index,
                record.row_header,
                record.col_header,
                record.caption,
            )
            for record in structure.table_cells
        ],
    )


def insert_issues(conn: sqlite3.Connection, structure: DocumentStructure) -> None:
    conn.executemany(
        f"INSERT INTO structure_issues (document_id, pdf_page, code, detail) VALUES ({_marks(4)})",
        [(structure.document_id, issue.pdf_page, issue.code, issue.detail) for issue in structure.issues],
    )


def insert_fts(conn: sqlite3.Connection, structure: DocumentStructure) -> None:
    """Index the body-retrieval units only. Header and footer units never enter the FTS table."""
    conn.executemany(
        f"INSERT INTO evidence_fts (index_text, heading_text, evidence_id, document_id) VALUES ({_marks(4)})",
        [
            (unit.index_text, unit.heading_text, unit.evidence_id, unit.document_id)
            for unit in structure.units
            if unit.body_retrieval
        ],
    )


def insert_evaluation(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    created_at: str,
    split: str,
    config_json: str,
    metrics_json: str,
    dataset_sha256: str,
) -> None:
    """One row of the ``evaluations`` table (ARCHITECTURE §17.12). The JSON texts are already canonical."""
    conn.execute(
        f"INSERT INTO evaluations (run_id, created_at, split, config_json, metrics_json, dataset_sha256) "
        f"VALUES ({_marks(6)})",
        (run_id, created_at, split, config_json, metrics_json, dataset_sha256),
    )


# ----------------------------------------------------------------------------- reads


def read_evaluation(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT run_id, created_at, split, config_json, metrics_json, dataset_sha256 FROM evaluations WHERE run_id = ?",
        (run_id,),
    ).fetchone()


def read_document_ids(conn: sqlite3.Connection) -> list[str]:
    return [row[0] for row in conn.execute("SELECT document_id FROM documents ORDER BY document_id")]


def read_document_row(conn: sqlite3.Connection, document_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()


def read_sections(conn: sqlite3.Connection, document_id: str) -> list[Section]:
    rows = conn.execute(
        "SELECT section_id, document_id, level, title, parent_section_id, start_pdf_page, heading_id "
        "FROM sections WHERE document_id = ? ORDER BY position",
        (document_id,),
    ).fetchall()
    return [
        Section(
            section_id=row["section_id"],
            document_id=row["document_id"],
            level=row["level"],
            title=row["title"],
            parent_section_id=row["parent_section_id"],
            start_pdf_page=row["start_pdf_page"],
            heading_id=row["heading_id"],
        )
        for row in rows
    ]


def _unit_filter(
    document_id: str,
    fts_match: str | None,
    evidence_id: str | None,
) -> tuple[str, list[Any]]:
    """The WHERE clause for units of one document, optionally narrowed by FTS match or by ID.

    The FTS subquery is scoped to the same document, so a candidate from another document can never
    be returned.
    """
    clauses = ["u.document_id = ?"]
    params: list[Any] = [document_id]
    if fts_match is not None:
        clauses.append(
            "u.evidence_id IN (SELECT evidence_id FROM evidence_fts "
            "WHERE evidence_fts MATCH ? AND document_id = ?)"
        )
        params.extend([fts_match, document_id])
    if evidence_id is not None:
        clauses.append("u.evidence_id = ?")
        params.append(evidence_id)
    return " AND ".join(clauses), params


def read_units(
    conn: sqlite3.Connection,
    document_id: str,
    *,
    fts_match: str | None = None,
    evidence_id: str | None = None,
) -> list[EvidenceUnit]:
    """Units of one document in page order, each with its spans in span order."""
    where, params = _unit_filter(document_id, fts_match, evidence_id)
    rows = conn.execute(
        f"SELECT u.* FROM evidence_units AS u WHERE {where} ORDER BY u.pdf_page, u.ordinal",
        params,
    ).fetchall()
    span_rows = conn.execute(
        "SELECT s.evidence_id, s.source_start, s.source_end FROM source_locations AS s "
        f"WHERE s.evidence_id IN (SELECT u.evidence_id FROM evidence_units AS u WHERE {where}) "
        "ORDER BY s.evidence_id, s.span_index",
        params,
    ).fetchall()
    spans: dict[str, list[tuple[int, int]]] = {}
    for span in span_rows:
        spans.setdefault(span["evidence_id"], []).append((span["source_start"], span["source_end"]))
    return [_unit_from_row(row, spans.get(row["evidence_id"], [])) for row in rows]


def _unit_from_row(row: sqlite3.Row, spans: list[tuple[int, int]]) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_id=row["evidence_id"],
        document_id=row["document_id"],
        pdf_page=row["pdf_page"],
        printed_page=row["printed_page"],
        ordinal=row["ordinal"],
        content_type=ContentType(row["content_type"]),
        raw_text=row["raw_text"],
        source_spans=spans,
        index_text=row["index_text"],
        heading_text=row["heading_text"],
        section_id=row["section_id"],
        parent_id=row["parent_id"],
        prev_id=row["prev_id"],
        next_id=row["next_id"],
        bbox=(row["x0"], row["y0"], row["x1"], row["y1"]),
        table_id=row["table_id"],
        row_index=row["row_index"],
        col_index=row["col_index"],
        row_header=row["row_header"],
        col_header=row["col_header"],
        caption=row["caption"],
        extraction_quality=QualityStatus(row["extraction_quality"]),
        body_retrieval=bool(row["body_retrieval"]),
        derived=bool(row["derived"]),
    )


def read_table_cells(conn: sqlite3.Connection, document_id: str) -> list[TableCell]:
    rows = conn.execute(
        "SELECT t.evidence_id, t.table_id, t.row_index, t.col_index, t.row_header, t.col_header, t.caption "
        "FROM table_cells AS t JOIN evidence_units AS u ON u.evidence_id = t.evidence_id "
        "WHERE u.document_id = ? ORDER BY u.pdf_page, u.ordinal",
        (document_id,),
    ).fetchall()
    return [
        TableCell(
            evidence_id=row["evidence_id"],
            table_id=row["table_id"],
            row_index=row["row_index"],
            col_index=row["col_index"],
            row_header=row["row_header"],
            col_header=row["col_header"],
            caption=row["caption"],
        )
        for row in rows
    ]


def read_issues(conn: sqlite3.Connection, document_id: str) -> list[StructureIssue]:
    rows = conn.execute(
        "SELECT pdf_page, code, detail FROM structure_issues WHERE document_id = ? ORDER BY issue_id",
        (document_id,),
    ).fetchall()
    return [StructureIssue(pdf_page=row["pdf_page"], code=row["code"], detail=row["detail"]) for row in rows]


def read_page_texts(conn: sqlite3.Connection, document_id: str, pdf_pages: Iterable[int]) -> dict[int, str]:
    """The immutable raw text of the requested pages. A page that is missing is an integrity error."""
    wanted = sorted(set(pdf_pages))
    found: dict[int, str] = {}
    for chunk in _chunks(wanted, _PAGE_CHUNK):
        rows = conn.execute(
            f"SELECT pdf_page, raw_text FROM pages WHERE document_id = ? AND pdf_page IN ({_marks(len(chunk))})",
            (document_id, *chunk),
        ).fetchall()
        found.update({row["pdf_page"]: row["raw_text"] for row in rows})
    missing = [page for page in wanted if page not in found]
    if missing:
        raise StorageIntegrityError(f"document {document_id} has no stored text for pages {missing}")
    return found


def read_page_warning_codes(conn: sqlite3.Connection, document_id: str, pdf_page: int) -> tuple[str, ...]:
    """The issue codes stored for one page (``pages.warnings_json``), in the order they were written (P6, D62)."""
    row = conn.execute(
        "SELECT warnings_json FROM pages WHERE document_id = ? AND pdf_page = ?",
        (document_id, pdf_page),
    ).fetchone()
    if row is None:
        raise StorageIntegrityError(f"document {document_id} has no stored page {pdf_page}")
    return tuple(str(issue["code"]) for issue in json.loads(row["warnings_json"]))


def read_page_extraction_method(conn: sqlite3.Connection, document_id: str, pdf_page: int) -> str:
    """The extraction method stored for one page (``pages.extraction_method``): native text, OCR or none (P7)."""
    row = conn.execute(
        "SELECT extraction_method FROM pages WHERE document_id = ? AND pdf_page = ?",
        (document_id, pdf_page),
    ).fetchone()
    if row is None:
        raise StorageIntegrityError(f"document {document_id} has no stored page {pdf_page}")
    return str(row["extraction_method"])


def read_structure(conn: sqlite3.Connection, document_id: str, row: sqlite3.Row) -> DocumentStructure:
    """Rebuild a DocumentStructure exactly as it was written."""
    return DocumentStructure(
        structure_version=row["structure_version"],
        document_id=document_id,
        config_sha256=row["structure_config_sha256"],
        sections=read_sections(conn, document_id),
        units=read_units(conn, document_id),
        table_cells=read_table_cells(conn, document_id),
        issues=read_issues(conn, document_id),
    )
