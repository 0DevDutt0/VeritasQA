"""Build the document structure from a P1 extraction (ARCHITECTURE §11).

``build_structure`` runs in three passes over the pages. Pass 1 measures the body size and plans every
structured page. Pass 2 ranks the heading sizes across the document. Pass 3 emits the units, the
sections and the table cells, in page order, and links the neighbours.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Sequence

from app.common.text import normalize_text
from app.document_structure.config import StructureConfig, load_structure_config
from app.document_structure.errors import StructureError
from app.document_structure.models import (
    ContentType,
    DocumentStructure,
    EvidenceUnit,
    Section,
    StructureIssue,
    TableCell,
)
from app.document_structure.segment import (
    PagePlan,
    Pending,
    body_size,
    heading_level,
    heading_size_levels,
    plan_page,
)
from app.document_structure.tables import read_table_geometry
from app.ingestion.models import Box, BlockRole, ExtractedDocument, ExtractedPage, Line, QualityStatus

_NUMERIC_TEXT = re.compile(r"^[\d\s.,%$()+\-–]+$")
_STRUCTURED = frozenset({QualityStatus.VERIFIED, QualityStatus.WARNING})
_PENDING_CONTENT = {
    "paragraph": ContentType.PARAGRAPH,
    "list_item": ContentType.LIST_ITEM,
    "caption": ContentType.CAPTION,
    "footnote": ContentType.FOOTNOTE,
}
# A caption is attached to a table when it lies within this share of the page height from the table box.
_CAPTION_REACH = 0.15


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(lines: Sequence[Line]) -> str:
    return " ".join(" ".join(line.text.split()) for line in lines)


def _union(boxes: Sequence[Box]) -> Box:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _spans(lines: Sequence[Line], raw: str) -> list[tuple[int, int]]:
    """Raw offsets of the lines. Lines separated by exactly one newline in the raw text share a span."""
    spans: list[tuple[int, int]] = []
    for line in lines:
        start, end = line.raw_start, line.raw_end
        if raw[start:end] != line.text:
            raise StructureError("the raw text does not match an extracted line; the report is inconsistent")
        if spans and start >= spans[-1][1] and raw[spans[-1][1] : start] == "\n":
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    return spans


class _Emitter:
    """Turns the planned pages into units, sections and table cells, in document order."""

    def __init__(self, extracted: ExtractedDocument, config: StructureConfig, body: float, size_levels: list[float]) -> None:
        self.document_id = extracted.document_id
        self.config = config
        self.body = body
        self.size_levels = size_levels
        self.units: list[EvidenceUnit] = []
        self.sections: list[Section] = []
        self.table_cells: list[TableCell] = []
        self.issues: list[StructureIssue] = []
        self.stack: list[Section] = []
        self.open_intro: str | None = None
        self.page: ExtractedPage | None = None
        self.ordinal = 0
        self.tables_on_page = 0

    def start_page(self, page: ExtractedPage) -> None:
        self.page = page
        self.ordinal = 0
        self.tables_on_page = 0

    def _page(self) -> ExtractedPage:
        if self.page is None:
            raise StructureError("no page has been started")
        return self.page

    def _section_id(self) -> str | None:
        return self.stack[-1].section_id if self.stack else None

    def _heading_chain(self, extra: str | None = None) -> str:
        titles = [section.title for section in self.stack] + ([extra] if extra else [])
        return " > ".join(titles)

    def _quality(self, lines: Sequence[Line], warn: bool = False) -> QualityStatus:
        page_quality = self._page().quality_status
        if any(line.hidden_chars > 0 for line in lines):
            return QualityStatus.UNVERIFIED
        if warn and page_quality == QualityStatus.VERIFIED:
            return QualityStatus.WARNING
        return page_quality

    def add(
        self,
        content_type: ContentType,
        lines: Sequence[Line],
        *,
        section_id: str | None = None,
        parent_id: str | None = None,
        body_retrieval: bool = True,
        derived: bool = False,
        index_source: str | None = None,
        heading_text: str | None = None,
        quality: QualityStatus | None = None,
        table_id: str | None = None,
        row_index: int | None = None,
        col_index: int | None = None,
        row_header: str | None = None,
        col_header: str | None = None,
        caption: str | None = None,
    ) -> EvidenceUnit:
        page = self._page()
        raw = page.raw_text
        spans = _spans(lines, raw)
        text = "\n".join(line.text for line in lines)
        if "\n".join(raw[start:end] for start, end in spans) != text:
            raise StructureError("the source spans do not reproduce the unit text")
        self.ordinal += 1
        unit = EvidenceUnit(
            evidence_id=f"{self.document_id}:p{page.pdf_page:04d}:u{self.ordinal:04d}",
            document_id=self.document_id,
            pdf_page=page.pdf_page,
            printed_page=page.printed_page,
            ordinal=self.ordinal,
            content_type=content_type,
            raw_text=text,
            source_spans=spans,
            index_text=normalize_text(index_source if index_source is not None else text),
            heading_text=heading_text if heading_text is not None else self._heading_chain(),
            section_id=section_id,
            parent_id=parent_id,
            bbox=_union([line.bbox for line in lines]),
            table_id=table_id,
            row_index=row_index,
            col_index=col_index,
            row_header=row_header,
            col_header=col_header,
            caption=caption,
            extraction_quality=quality if quality is not None else self._quality(lines),
            body_retrieval=body_retrieval,
            derived=derived,
        )
        self.units.append(unit)
        return unit

    def emit_unstructured(self, page: ExtractedPage) -> None:
        """A page that is not OK or WARNING gets block-level units only, all unverified (ARCHITECTURE §11)."""
        self.issues.append(
            StructureIssue(
                pdf_page=page.pdf_page,
                code="page_unstructured",
                detail=f"page status {page.status.value}: no sections, headings or tables are built here",
            )
        )
        for block in page.blocks:
            if not block.lines:
                continue
            if block.role == BlockRole.HEADER:
                self.add(ContentType.HEADER, block.lines, body_retrieval=False)
            elif block.role == BlockRole.FOOTER:
                self.add(ContentType.FOOTER, block.lines, body_retrieval=False)
            elif block.role in (BlockRole.BODY, BlockRole.OCR):
                self.add(ContentType.PAGE_TEXT, block.lines, quality=QualityStatus.UNVERIFIED)

    def emit_structured(self, page: ExtractedPage, plan: PagePlan) -> None:
        for block in page.blocks:
            if block.role == BlockRole.HEADER and block.lines:
                self.add(ContentType.HEADER, block.lines, body_retrieval=False)
        for pending in plan.pendings:
            self._emit_pending(page, plan, pending)
        for block in page.blocks:
            if block.role == BlockRole.FOOTER and block.lines:
                self.add(ContentType.FOOTER, block.lines, body_retrieval=False)

    def _emit_pending(self, page: ExtractedPage, plan: PagePlan, pending: Pending) -> None:
        if pending.kind == "furniture":
            rec = pending.lines[0]
            content = ContentType.HEADER if rec.bbox[1] < page.height / 2 else ContentType.FOOTER
            self.add(content, [rec.line], body_retrieval=False)
            return
        if pending.kind == "table":
            assert pending.table is not None
            self._emit_table(page, plan, pending.table)
            return
        lines = [rec.line for rec in pending.lines]
        if pending.kind == "heading":
            self._emit_heading(lines, pending)
            return
        content = _PENDING_CONTENT[pending.kind]
        parent = self.open_intro if pending.kind == "list_item" else None
        unit = self.add(content, lines, section_id=self._section_id(), parent_id=parent)
        if pending.kind == "list_item":
            return
        self.open_intro = unit.evidence_id if pending.kind == "paragraph" and unit.raw_text.rstrip().endswith(":") else None

    def _emit_heading(self, lines: Sequence[Line], pending: Pending) -> None:
        title = _text(lines)
        level = heading_level(pending, self.body, self.size_levels, self.config)
        while self.stack and self.stack[-1].level >= level:
            self.stack.pop()
        parent = self.stack[-1] if self.stack else None
        section_id = f"{self.document_id}:s{len(self.sections) + 1:04d}"
        unit = self.add(
            ContentType.HEADING,
            lines,
            section_id=section_id,
            parent_id=parent.heading_id if parent else None,
            heading_text=self._heading_chain(extra=title),
        )
        section = Section(
            section_id=section_id,
            document_id=self.document_id,
            level=level,
            title=title,
            parent_section_id=parent.section_id if parent else None,
            start_pdf_page=self._page().pdf_page,
            heading_id=unit.evidence_id,
        )
        self.sections.append(section)
        self.stack.append(section)
        self.open_intro = None

    def _caption_for(self, plan: PagePlan, table_box: Box) -> str | None:
        page = self._page()
        reach = _CAPTION_REACH * page.height
        best = None
        best_gap = None
        for caption in plan.captions:
            caption_box = caption.bbox
            gap = max(0.0, table_box[1] - caption_box[3], caption_box[1] - table_box[3])
            if gap <= reach and (best_gap is None or gap < best_gap):
                best, best_gap = caption, gap
        return best.text if best is not None else None

    def _emit_table(self, page: ExtractedPage, plan: PagePlan, table_index: int) -> None:
        geometry = plan.tables[table_index]
        cells = plan.cells[table_index]
        self.tables_on_page += 1
        table_id = f"{self.document_id}:p{page.pdf_page:04d}:t{self.tables_on_page:02d}"
        caption = self._caption_for(plan, geometry.bbox)
        column_count = max((len(row) for row in geometry.rows), default=0)
        header = {column: _text([rec.line for rec in cells[(0, column)]]) if (0, column) in cells else "" for column in range(column_count)}
        filled = [value for value in header.values() if value]
        uncertain = bool(filled) and all(_NUMERIC_TEXT.match(value) for value in filled)
        if uncertain:
            self.issues.append(
                StructureIssue(
                    pdf_page=page.pdf_page,
                    code="table_header_uncertain",
                    detail=f"{table_id}: every header cell is numeric, so the first row may be data",
                )
            )
        section_id = self._section_id()
        for column in range(column_count):
            if (0, column) in cells:
                lines = [rec.line for rec in cells[(0, column)]]
                self._cell_unit(lines, table_id, 0, column, None, None, caption, header[column], uncertain, section_id, None)
        for row_index in range(1, len(geometry.rows)):
            row_cells = [(column, cells[(row_index, column)]) for column in range(column_count) if (row_index, column) in cells]
            if not row_cells:
                continue
            row_header = _text([rec.line for rec in cells[(row_index, 0)]]) if (row_index, 0) in cells else ""
            row_header = row_header or None
            pairs = "; ".join(
                f"{header[column]} = {_text([rec.line for rec in lines])}"
                for column, lines in row_cells
                if column != 0 and header[column]
            )
            row_unit = self.add(
                ContentType.TABLE_ROW,
                [rec.line for _, lines in row_cells for rec in lines],
                section_id=section_id,
                derived=True,
                index_source=" | ".join(part for part in (caption, row_header, pairs) if part),
                quality=self._quality([rec.line for _, lines in row_cells for rec in lines], warn=uncertain),
                table_id=table_id,
                row_index=row_index,
                row_header=row_header,
                caption=caption,
            )
            for column, lines in row_cells:
                self._cell_unit(
                    [rec.line for rec in lines],
                    table_id,
                    row_index,
                    column,
                    row_header if column != 0 else None,
                    header[column] or None,
                    caption,
                    _text([rec.line for rec in lines]),
                    uncertain,
                    section_id,
                    row_unit.evidence_id,
                )

    def _cell_unit(
        self,
        lines: Sequence[Line],
        table_id: str,
        row_index: int,
        column: int,
        row_header: str | None,
        col_header: str | None,
        caption: str | None,
        value: str,
        uncertain: bool,
        section_id: str | None,
        parent_id: str | None,
    ) -> None:
        parts = [caption, row_header, col_header if row_index >= 1 else None, value]
        unit = self.add(
            ContentType.TABLE_CELL,
            lines,
            section_id=section_id,
            parent_id=parent_id,
            index_source=" | ".join(part for part in parts if part),
            quality=self._quality(lines, warn=uncertain),
            table_id=table_id,
            row_index=row_index,
            col_index=column,
            row_header=row_header,
            col_header=col_header if row_index >= 1 else None,
            caption=caption,
        )
        self.table_cells.append(
            TableCell(
                evidence_id=unit.evidence_id,
                table_id=table_id,
                row_index=row_index,
                col_index=column,
                row_header=row_header,
                col_header=col_header if row_index >= 1 else None,
                caption=caption,
            )
        )

    def finish(self) -> None:
        for index, unit in enumerate(self.units):
            unit.prev_id = self.units[index - 1].evidence_id if index > 0 else None
            unit.next_id = self.units[index + 1].evidence_id if index + 1 < len(self.units) else None

    def result(self) -> DocumentStructure:
        return DocumentStructure(
            document_id=self.document_id,
            sections=self.sections,
            units=self.units,
            table_cells=self.table_cells,
            issues=self.issues,
        )


def build_structure(
    extracted: ExtractedDocument,
    pdf_path: Path | str,
    *,
    config: StructureConfig | None = None,
) -> DocumentStructure:
    """Build sections, evidence units and table cells for one extracted document.

    ``pdf_path`` is read only for table geometry, and only after its SHA-256 matches the report.
    Raises StructureError when the file does not match, or when the report is inconsistent.
    """
    settings = config if config is not None else load_structure_config()
    path = Path(pdf_path)
    if not path.is_file():
        raise StructureError(f"PDF not found: {path.name}")
    if _sha256(path) != extracted.sha256:
        raise StructureError("the PDF does not match the extraction report (SHA-256 differs)")

    structured = [page for page in extracted.pages if page.quality_status in _STRUCTURED]
    geometry = read_table_geometry(path, [page.pdf_page for page in structured if page.table_count])
    body = body_size(structured, settings)
    plans: dict[int, PagePlan] = {
        page.pdf_page: plan_page(page, geometry.get(page.pdf_page), body, settings) for page in structured
    }
    size_levels = heading_size_levels(list(plans.values()), body, settings)

    emitter = _Emitter(extracted, settings, body, size_levels)
    for page in extracted.pages:
        emitter.start_page(page)
        plan = plans.get(page.pdf_page)
        if plan is None:
            emitter.emit_unstructured(page)
        else:
            emitter.emit_structured(page, plan)
            for code, detail in plan.issues:
                emitter.issues.append(StructureIssue(pdf_page=page.pdf_page, code=code, detail=detail))
    emitter.finish()
    return emitter.result()
