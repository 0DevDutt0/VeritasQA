"""Property checks that every DocumentStructure must satisfy (ARCHITECTURE §11).

They need no ground truth, so they run on synthetic PDFs and on the public corpus alike. Each check
raises AssertionError with a message that names the unit or page at fault.
"""

from __future__ import annotations

from collections import defaultdict

from app.document_structure.models import ContentType, DocumentStructure
from app.ingestion.models import ExtractedDocument


def check_invariants(extracted: ExtractedDocument, structure: DocumentStructure) -> None:
    pages = {page.pdf_page: page for page in extracted.pages}
    units = structure.units
    assert structure.document_id == extracted.document_id

    ids = [unit.evidence_id for unit in units]
    assert len(ids) == len(set(ids)), "evidence IDs must be unique"

    per_page: dict[int, list] = defaultdict(list)
    for unit in units:
        page = pages[unit.pdf_page]
        per_page[unit.pdf_page].append(unit)
        expected_id = f"{extracted.document_id}:p{unit.pdf_page:04d}:u{unit.ordinal:04d}"
        assert unit.evidence_id == expected_id, f"ID of {unit.evidence_id} does not follow the ordinal rule"
        assert unit.printed_page == page.printed_page
        assert unit.raw_text, f"{unit.evidence_id} has no text"
        for start, end in unit.source_spans:
            assert 0 <= start < end <= len(page.raw_text), f"{unit.evidence_id} has a span outside its page"
        quoted = "\n".join(page.raw_text[start:end] for start, end in unit.source_spans)
        assert quoted == unit.raw_text, f"{unit.evidence_id}: the spans do not reproduce the unit text"
        if len(unit.source_spans) == 1:
            start, end = unit.source_spans[0]
            assert page.raw_text[start:end] == unit.raw_text, f"{unit.evidence_id}: a single span must be verbatim"
        else:
            assert unit.content_type in (ContentType.TABLE_CELL, ContentType.TABLE_ROW), (
                f"{unit.evidence_id}: only table units may have several spans (non-adjacent lines)"
            )
        if not unit.body_retrieval:
            assert unit.content_type in (ContentType.HEADER, ContentType.FOOTER), unit.evidence_id
        if unit.derived:
            assert unit.content_type == ContentType.TABLE_ROW, unit.evidence_id
        if unit.extraction_quality.value == "verified":
            assert page.quality_status.value == "verified", f"{unit.evidence_id} is verified on a non-OK page"

    for page_number, page_units in per_page.items():
        ordinals = [unit.ordinal for unit in page_units]
        assert ordinals == list(range(1, len(page_units) + 1)), f"page {page_number}: ordinals are not contiguous"

    for previous, following in zip(units, units[1:]):
        assert previous.next_id == following.evidence_id, "next_id must point to the following unit"
        assert following.prev_id == previous.evidence_id, "prev_id must point to the preceding unit"
    if units:
        assert units[0].prev_id is None and units[-1].next_id is None

    section_by_id = {section.section_id: section for section in structure.sections}
    for section in structure.sections:
        if section.parent_section_id is not None:
            parent = section_by_id[section.parent_section_id]
            assert parent.level < section.level, f"{section.section_id}: parent level must be lower"
    for unit in units:
        if unit.section_id is not None:
            assert unit.section_id in section_by_id, f"{unit.evidence_id} points to a missing section"

    for page_number, page in pages.items():
        covered = [False] * len(page.raw_text)
        for unit in per_page.get(page_number, []):
            if unit.derived:
                continue
            for start, end in unit.source_spans:
                for index in range(start, end):
                    if covered[index]:
                        raise AssertionError(f"{unit.evidence_id} overlaps another unit at offset {index}")
                    covered[index] = True
        for index, character in enumerate(page.raw_text):
            if not character.isspace():
                assert covered[index], f"page {page_number}: non-space text at offset {index} is in no unit"

    cells = [unit for unit in units if unit.content_type == ContentType.TABLE_CELL]
    assert [cell.evidence_id for cell in cells] == [record.evidence_id for record in structure.table_cells]
    for record in structure.table_cells:
        cell = next(unit for unit in cells if unit.evidence_id == record.evidence_id)
        assert cell.table_id == record.table_id and cell.row_index == record.row_index
        assert cell.col_index == record.col_index
