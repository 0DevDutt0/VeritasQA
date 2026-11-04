"""Typed records for P2 structure. The vocabulary is part of the contract in docs/ARCHITECTURE.md §11."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.ingestion.models import Box, QualityStatus

STRUCTURE_VERSION = "p2-structure-1"


class ContentType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    TABLE_CELL = "table_cell"
    TABLE_ROW = "table_row"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_TEXT = "page_text"


class Section(BaseModel):
    section_id: str
    document_id: str
    level: int = Field(ge=1)
    title: str
    parent_section_id: str | None
    start_pdf_page: int = Field(ge=1)
    heading_id: str


class EvidenceUnit(BaseModel):
    """One unit of evidence. ``raw_text`` is quoted; ``index_text`` is only for retrieval."""

    evidence_id: str
    document_id: str
    pdf_page: int = Field(ge=1)
    printed_page: str | None
    ordinal: int = Field(ge=1)
    content_type: ContentType
    raw_text: str
    # Half-open offsets into the page's raw_text. Invariant:
    # "\n".join(raw_text_of_page[start:end] for start, end in source_spans) == raw_text.
    source_spans: list[tuple[int, int]]
    index_text: str
    heading_text: str = ""
    section_id: str | None = None
    parent_id: str | None = None
    prev_id: str | None = None
    next_id: str | None = None
    bbox: Box
    table_id: str | None = None
    row_index: int | None = None
    col_index: int | None = None
    row_header: str | None = None
    col_header: str | None = None
    caption: str | None = None
    extraction_quality: QualityStatus
    body_retrieval: bool = True
    derived: bool = False


class TableCell(BaseModel):
    """The table_cells record of ARCHITECTURE §6, one per table cell unit."""

    evidence_id: str
    table_id: str
    row_index: int = Field(ge=0)
    col_index: int = Field(ge=0)
    row_header: str | None
    col_header: str | None
    caption: str | None


class StructureIssue(BaseModel):
    """A page-level finding made while structuring. It explains a skipped or uncertain step."""

    pdf_page: int = Field(ge=1)
    code: str
    detail: str


class DocumentStructure(BaseModel):
    structure_version: str = STRUCTURE_VERSION
    document_id: str
    config_sha256: str = ""
    sections: list[Section] = Field(default_factory=list)
    units: list[EvidenceUnit] = Field(default_factory=list)
    table_cells: list[TableCell] = Field(default_factory=list)
    issues: list[StructureIssue] = Field(default_factory=list)


# Issue codes emitted by P2. Tests check that every emitted code belongs to this set.
STRUCTURE_ISSUE_CODES = frozenset(
    {
        "table_geometry_mismatch",
        "table_read_failed",
        "table_header_uncertain",
        "page_unstructured",
    }
)
