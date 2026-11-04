"""Checks that run before a document is written (ARCHITECTURE §6, write rules).

They read only their inputs and touch no database, so a failing record leaves the store unchanged.
Each failure raises :class:`StorageIntegrityError` and names the record at fault.
"""

from __future__ import annotations

import hashlib
from collections.abc import Hashable, Iterable

from app.common.errors import StorageIntegrityError
from app.document_structure.models import ContentType, DocumentStructure, EvidenceUnit
from app.ingestion.models import ExtractedDocument


def _fail(message: str) -> None:
    raise StorageIntegrityError(message)


def _require_unique(values: Iterable[Hashable], what: str) -> set[Hashable]:
    seen: set[Hashable] = set()
    for value in values:
        if value in seen:
            _fail(f"{what} {value!r} occurs more than once")
        seen.add(value)
    return seen


def check_for_write(extracted: ExtractedDocument, structure: DocumentStructure) -> None:
    """Raise :class:`StorageIntegrityError` on the first inconsistency between the two records."""
    document_id = extracted.document_id
    if structure.document_id != document_id:
        _fail(f"the structure belongs to {structure.document_id}, not to {document_id}")
    if len(extracted.pages) != extracted.page_count:
        _fail(f"the report lists {len(extracted.pages)} pages but states {extracted.page_count}")

    page_texts: dict[int, str] = {}
    for number, page in enumerate(extracted.pages, start=1):
        if page.pdf_page != number:
            _fail(f"page {number} is recorded as page {page.pdf_page}")
        digest = hashlib.sha256(page.raw_text.encode("utf-8")).hexdigest()
        if digest != page.raw_text_sha256:
            _fail(f"page {number}: raw_text does not match its raw_text_sha256")
        page_texts[number] = page.raw_text

    for issue in structure.issues:
        if issue.pdf_page not in page_texts:
            _fail(f"a structure issue names page {issue.pdf_page}, which the document does not have")

    section_ids = _require_unique((section.section_id for section in structure.sections), "section_id")
    for section in structure.sections:
        if section.document_id != document_id:
            _fail(f"section {section.section_id} belongs to another document")
        if section.parent_section_id is not None and section.parent_section_id not in section_ids:
            _fail(f"section {section.section_id} names a missing parent {section.parent_section_id}")

    unit_ids = _require_unique((unit.evidence_id for unit in structure.units), "evidence_id")
    _require_unique(((unit.pdf_page, unit.ordinal) for unit in structure.units), "page and ordinal")
    units_by_id: dict[str, EvidenceUnit] = {unit.evidence_id: unit for unit in structure.units}
    for unit in structure.units:
        _check_unit(unit, document_id, page_texts, section_ids, unit_ids)

    for section in structure.sections:
        if section.heading_id not in unit_ids:
            _fail(f"section {section.section_id} names a missing heading unit {section.heading_id}")

    _require_unique((record.evidence_id for record in structure.table_cells), "table cell evidence_id")
    for record in structure.table_cells:
        unit = units_by_id.get(record.evidence_id)
        if unit is None or unit.content_type != ContentType.TABLE_CELL:
            _fail(f"table cell record {record.evidence_id} does not name a table cell unit")
        unit_fields = (unit.table_id, unit.row_index, unit.col_index, unit.row_header, unit.col_header, unit.caption)
        record_fields = (
            record.table_id,
            record.row_index,
            record.col_index,
            record.row_header,
            record.col_header,
            record.caption,
        )
        if unit_fields != record_fields:
            _fail(f"table cell record {record.evidence_id} disagrees with its unit")


def _check_unit(
    unit: EvidenceUnit,
    document_id: str,
    page_texts: dict[int, str],
    section_ids: set[Hashable],
    unit_ids: set[Hashable],
) -> None:
    if unit.document_id != document_id:
        _fail(f"unit {unit.evidence_id} belongs to another document")
    raw = page_texts.get(unit.pdf_page)
    if raw is None:
        _fail(f"unit {unit.evidence_id} is on page {unit.pdf_page}, which the document does not have")
    if not unit.source_spans:
        _fail(f"unit {unit.evidence_id} has no source spans")
    for start, end in unit.source_spans:
        if not 0 <= start < end <= len(raw):
            _fail(f"unit {unit.evidence_id} has the span ({start}, {end}) outside its page text")
    quoted = "\n".join(raw[start:end] for start, end in unit.source_spans)
    if quoted != unit.raw_text:
        _fail(f"unit {unit.evidence_id}: its spans do not reproduce its raw_text")
    if unit.section_id is not None and unit.section_id not in section_ids:
        _fail(f"unit {unit.evidence_id} names a missing section {unit.section_id}")
    for reference in (unit.parent_id, unit.prev_id, unit.next_id):
        if reference is not None and reference not in unit_ids:
            _fail(f"unit {unit.evidence_id} names a missing unit {reference}")
