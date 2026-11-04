"""Typed records for ingestion. The JSON form of ExtractedDocument is the extraction report.

The vocabulary (statuses, roles, issue codes) is part of the contract in docs/ARCHITECTURE.md §10.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Box = tuple[float, float, float, float]


class PageStatus(StrEnum):
    OK = "OK"
    WARNING = "WARNING"
    SCANNED = "SCANNED"
    SCANNED_TEXT_LAYER = "SCANNED_TEXT_LAYER"
    OCR_TEXT = "OCR_TEXT"
    BLANK = "BLANK"
    GARBLED = "GARBLED"
    SUSPICIOUS = "SUSPICIOUS"


class QualityStatus(StrEnum):
    VERIFIED = "verified"
    WARNING = "warning"
    UNVERIFIED = "unverified"


class ExtractionMethod(StrEnum):
    NATIVE_TEXT = "native_text"
    OCR_TESSERACT = "ocr_tesseract"
    NONE = "none"


class BlockRole(StrEnum):
    BODY = "body"
    HEADER = "header"
    FOOTER = "footer"
    IMAGE = "image"
    OCR = "ocr"


class ReadingOrder(StrEnum):
    NONE = "none"
    SINGLE_COLUMN = "single_column"
    MULTI_COLUMN = "multi_column"


# Every issue code the extractor can emit. Tests check that emitted codes belong to this set.
ISSUE_CODES = frozenset(
    {
        # document level, also stamped on every page when they apply
        "pdf_repaired",
        "pdf_missing_eof",
        "mupdf_messages",
        # page level
        "page_rotated",
        "blank_page",
        "image_only_page",
        "image_with_text_layer",
        "hidden_text_layer",
        "hidden_text_only",
        "hidden_text_share_high",
        "hidden_text_present",
        "text_render_mode_unknown",
        "no_text_with_content",
        "garbled_text",
        "suspicious_text",
        "table_detected",
        "table_check_failed",
        "reading_order_uncertain",
        "ocr_unavailable",
        "ocr_disabled",
        "ocr_failed",
        "ocr_no_text",
        "ocr_text_unverified",
    }
)


def quality_for(status: PageStatus) -> QualityStatus:
    """Map a page status to the evidence quality state (ARCHITECTURE §10)."""
    if status is PageStatus.OK:
        return QualityStatus.VERIFIED
    if status is PageStatus.WARNING:
        return QualityStatus.WARNING
    return QualityStatus.UNVERIFIED


class Issue(BaseModel):
    """One explained finding. Only severity ``warning`` can change a page status."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["info", "warning"]
    detail: str


class Span(BaseModel):
    text: str
    bbox: Box
    font: str
    size: float
    flags: int
    bold: bool


class Line(BaseModel):
    raw_start: int
    raw_end: int
    bbox: Box
    text: str
    spans: list[Span] = Field(default_factory=list)
    # Invisible characters (render mode 3 or 7) whose glyph centre lies in this line. A line with
    # hidden_chars > 0 is unverified evidence, and P2 must not ground an answer on it (D20).
    hidden_chars: int = 0


class Block(BaseModel):
    block_no: int
    role: BlockRole
    bbox: Box
    reading_index: int | None = None
    column_index: int | None = None
    raw_start: int | None = None
    raw_end: int | None = None
    lines: list[Line] = Field(default_factory=list)


class ExtractedPage(BaseModel):
    pdf_page: int = Field(ge=1)
    printed_page: str | None
    width: float
    height: float
    rotation: int
    status: PageStatus
    quality_status: QualityStatus
    extraction_method: ExtractionMethod
    visible_chars: int | None
    hidden_chars: int | None
    non_space_chars: int
    image_coverage: float
    ink_ratio: float | None
    table_count: int | None
    column_count: int
    reading_order: ReadingOrder
    reading_order_uncertain: bool
    issues: list[Issue] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    # The immutable page text. It is written to pages/pNNNN.txt, not into the JSON report.
    raw_text: str = Field(exclude=True)
    raw_text_sha256: str
    raw_text_path: str | None = None
    render_path: str | None = None


class PdfFileInfo(BaseModel):
    source_name: str
    size_bytes: int
    sha256: str
    document_id: str
    page_count: int
    is_repaired: bool
    has_eof_marker: bool


class ExtractedDocument(BaseModel):
    """The per-document extraction report. It has no timestamps and no absolute paths."""

    schema_version: int = 1
    extractor_version: str
    pymupdf_version: str
    pdfplumber_version: str
    config_sha256: str
    document_id: str
    source_name: str
    size_bytes: int
    sha256: str
    page_count: int
    status_counts: dict[str, int]
    issues: list[Issue] = Field(default_factory=list)
    pages: list[ExtractedPage] = Field(default_factory=list)
