"""Hand-built P1 and P2 records for the P3 store and phrase tests (labelled synthetic).

No PDF is involved. Every page text, span and unit is written out, so each expected result is known
exactly. ``sample_document`` builds the same document under any ``document_id``, which lets the tests
put two documents with identical text into one store.
"""

from __future__ import annotations

import hashlib

from app.document_structure.models import ContentType, DocumentStructure, EvidenceUnit, Section, StructureIssue, TableCell
from app.ingestion.models import (
    ExtractedDocument,
    ExtractedPage,
    ExtractionMethod,
    PageStatus,
    QualityStatus,
    ReadingOrder,
    quality_for,
)
from app.common.text import normalize_text

DOC_A = "doc-" + "a" * 16
DOC_B = "doc-" + "b" * 16

PAGE_ONE = (
    "Risk Assessment Guide\n\n"
    "The threshold is 3.5 for high risk.\n\n"
    "Value 13.5 and 3.55 and 3.5.2 are listed.\n\n"
    "Risk. assessment is split here.\n\n"
    "risk and assessment are adjacent.\n\n"
    "assessment of the risk is reversed.\n\n"
    "Use ABC-123 and ABC 123 as identifiers.\n\n"
    "The café menu and the cafe list.\n\n"
    "Page 1 of 2"
)
PAGE_TWO = "Low\n1\nRare\n\nthe threshold is 3.5 for high risk."


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def span_of(text: str, fragment: str) -> tuple[int, int]:
    """Half-open offsets of the first occurrence of ``fragment`` in ``text``."""
    start = text.index(fragment)
    return start, start + len(fragment)


def make_page(pdf_page: int, raw_text: str, *, status: PageStatus = PageStatus.OK) -> ExtractedPage:
    return ExtractedPage(
        pdf_page=pdf_page,
        printed_page=None,
        width=612.0,
        height=792.0,
        rotation=0,
        status=status,
        quality_status=quality_for(status),
        extraction_method=ExtractionMethod.NATIVE_TEXT,
        visible_chars=len(raw_text),
        hidden_chars=0,
        non_space_chars=sum(not character.isspace() for character in raw_text),
        image_coverage=0.0,
        ink_ratio=None,
        table_count=0,
        column_count=1,
        reading_order=ReadingOrder.SINGLE_COLUMN,
        reading_order_uncertain=False,
        issues=[],
        blocks=[],
        raw_text=raw_text,
        raw_text_sha256=sha256_text(raw_text),
    )


def make_extracted(document_id: str, pages: list[ExtractedPage]) -> ExtractedDocument:
    return ExtractedDocument(
        extractor_version="p1-test",
        pymupdf_version="0.0.0",
        pdfplumber_version="0.0.0",
        config_sha256="c" * 64,
        document_id=document_id,
        source_name=f"{document_id}.pdf",
        size_bytes=1000,
        sha256="d" * 64,
        page_count=len(pages),
        status_counts={},
        issues=[],
        pages=pages,
    )


def make_unit(
    document_id: str,
    pdf_page: int,
    ordinal: int,
    content_type: ContentType,
    page_text: str,
    spans: list[tuple[int, int]],
    *,
    index_text: str | None = None,
    heading_text: str = "",
    section_id: str | None = None,
    body_retrieval: bool = True,
    derived: bool = False,
    table: dict | None = None,
) -> EvidenceUnit:
    raw_text = "\n".join(page_text[start:end] for start, end in spans)
    fields = {
        "table_id": None,
        "row_index": None,
        "col_index": None,
        "row_header": None,
        "col_header": None,
        "caption": None,
    }
    fields.update(table or {})
    return EvidenceUnit(
        evidence_id=f"{document_id}:p{pdf_page:04d}:u{ordinal:04d}",
        document_id=document_id,
        pdf_page=pdf_page,
        printed_page=None,
        ordinal=ordinal,
        content_type=content_type,
        raw_text=raw_text,
        source_spans=list(spans),
        index_text=index_text if index_text is not None else normalize_text(raw_text),
        heading_text=heading_text,
        section_id=section_id,
        bbox=(72.0, 100.0, 540.0, 120.0),
        extraction_quality=QualityStatus.VERIFIED,
        body_retrieval=body_retrieval,
        derived=derived,
        **fields,
    )


def link_units(units: list[EvidenceUnit]) -> None:
    """Chain the units of one document in order, as P2 does (ARCHITECTURE §11)."""
    for previous, following in zip(units, units[1:]):
        previous.next_id = following.evidence_id
        following.prev_id = previous.evidence_id


def sample_document(document_id: str = DOC_A) -> tuple[ExtractedDocument, DocumentStructure]:
    """A two-page synthetic document with headings, paragraphs, a footer, a table row and a cell."""
    pages = [make_page(1, PAGE_ONE), make_page(2, PAGE_TWO)]
    extracted = make_extracted(document_id, pages)

    section_id = f"{document_id}:s0001"
    heading = make_unit(
        document_id, 1, 1, ContentType.HEADING, PAGE_ONE, [span_of(PAGE_ONE, "Risk Assessment Guide")],
        heading_text="Risk Assessment Guide", section_id=section_id,
    )
    paragraph_fragments = [
        "The threshold is 3.5 for high risk.",
        "Value 13.5 and 3.55 and 3.5.2 are listed.",
        "Risk. assessment is split here.",
        "risk and assessment are adjacent.",
        "assessment of the risk is reversed.",
        "Use ABC-123 and ABC 123 as identifiers.",
        "The café menu and the cafe list.",
    ]
    units = [heading]
    for ordinal, fragment in enumerate(paragraph_fragments, start=2):
        units.append(
            make_unit(
                document_id, 1, ordinal, ContentType.PARAGRAPH, PAGE_ONE, [span_of(PAGE_ONE, fragment)],
                heading_text="Risk Assessment Guide", section_id=section_id,
            )
        )
    units.append(
        make_unit(
            document_id, 1, len(units) + 1, ContentType.FOOTER, PAGE_ONE, [span_of(PAGE_ONE, "Page 1 of 2")],
            body_retrieval=False,
        )
    )
    cell_spans = [span_of(PAGE_TWO, "Low"), span_of(PAGE_TWO, "1"), span_of(PAGE_TWO, "Rare")]
    row = make_unit(
        document_id, 2, 1, ContentType.TABLE_ROW, PAGE_TWO, cell_spans,
        index_text="Table 1 | Low | Rating = 1 ; Meaning = Rare",
        derived=True,
        table={"table_id": f"{document_id}:p0002:t01", "row_index": 1, "row_header": "Low", "caption": "Table 1"},
    )
    cell = make_unit(
        document_id, 2, 2, ContentType.TABLE_CELL, PAGE_TWO, [span_of(PAGE_TWO, "1")],
        index_text="Table 1 | Low | Rating | 1",
        table={
            "table_id": f"{document_id}:p0002:t01",
            "row_index": 1,
            "col_index": 1,
            "row_header": "Low",
            "col_header": "Rating",
            "caption": "Table 1",
        },
    )
    units.extend([row, cell])
    body = make_unit(
        document_id, 2, 3, ContentType.PARAGRAPH, PAGE_TWO,
        [span_of(PAGE_TWO, "the threshold is 3.5 for high risk.")],
        heading_text="Risk Assessment Guide", section_id=section_id,
    )
    units.append(body)
    link_units(units)
    sections = [
        Section(
            section_id=section_id,
            document_id=document_id,
            level=1,
            title="Risk Assessment Guide",
            parent_section_id=None,
            start_pdf_page=1,
            heading_id=heading.evidence_id,
        )
    ]
    cells = [
        TableCell(
            evidence_id=cell.evidence_id,
            table_id=cell.table_id,
            row_index=1,
            col_index=1,
            row_header="Low",
            col_header="Rating",
            caption="Table 1",
        )
    ]
    issues = [StructureIssue(pdf_page=2, code="table_header_uncertain", detail="synthetic issue for the round trip")]
    structure = DocumentStructure(
        document_id=document_id,
        config_sha256="e" * 64,
        sections=sections,
        units=units,
        table_cells=cells,
        issues=issues,
    )
    return extracted, structure
