"""Page segmentation for P2: classify P1 lines, claim table cells and group the lines into units.

Nothing here reads the PDF. The input is P1's ExtractedPage (its blocks and lines, with raw offsets),
and the optional table geometry. The output is a plan per page that build.py turns into EvidenceUnits.
The rules and their thresholds are in ARCHITECTURE §11 and config/structure.toml.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

from app.document_structure.config import StructureConfig
from app.document_structure.tables import PageGeometry, TableGeometry, assign_cells, count_inside
from app.ingestion.models import BlockRole, ExtractedPage, Line

BULLET_GLYPHS = "•·▪◦‣∙●○■□–*-"
_BULLET_ONLY = re.compile(rf"^[{re.escape(BULLET_GLYPHS)}]$")
_LIST_START = re.compile(
    rf"^(?:[{re.escape(BULLET_GLYPHS)}]\s+\S|\(?\d{{1,2}}[.)]\s+\S|\([A-Za-z]\)\s+\S|[a-z][.)]\s+\S)"
)
_CAPTION = re.compile(r"^(?:Table|Figure|Fig\.|Exhibit)\s+[A-Za-z]?\d+", re.IGNORECASE)
_NUMBER_LABEL = re.compile(r"^\d+(?:\.\d+)*\.?$")
_LABEL_PREFIX = re.compile(r"^(\d+(?:\.\d+)*)")
_FURNITURE = re.compile(r"^(?:\d+|[ivxlcdm]+)$", re.IGNORECASE)
_NO_HEADING_END = (".", ",", ";")
# A footnote starts with a marker: a number followed by a space, full stop or parenthesis, or a symbol (which may touch its text).
_FOOTNOTE_MARK = re.compile(r"^(?:\d{1,2}(?:[.)]\s|\s)|[*∗†‡§¶])")
_SENTENCE_END = (".", ":", ";", "!", "?")
_BOLD_TOLERANCE_PT = 0.5


@dataclass
class LineRec:
    """One P1 body line with the facts the rules need. ``kind`` and ``table`` are set in later steps."""

    block_index: int
    line: Line
    size: float
    bold: bool
    vertical: bool
    block_width: float
    column: int | None = None
    kind: str = "text"
    table: int | None = None
    cell: tuple[int, int] | None = None

    @property
    def text(self) -> str:
        return self.line.text.strip()

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return self.line.bbox

    @property
    def centre(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.line.bbox
        return ((x0 + x1) / 2, (y0 + y1) / 2)


@dataclass
class Pending:
    """A group of lines that will become one evidence unit (or one table, or one furniture line)."""

    kind: str
    lines: list[LineRec] = field(default_factory=list)
    table: int | None = None
    open_bullet: bool = False


@dataclass
class PagePlan:
    pdf_page: int
    recs: list[LineRec]
    pendings: list[Pending]
    tables: tuple[TableGeometry, ...]
    cells: dict[int, dict[tuple[int, int], list[LineRec]]]
    captions: list[LineRec]
    issues: list[tuple[str, str]]


def quantize(size: float, quantum: float) -> float:
    return round(round(size / quantum) * quantum, 3)


def _dominant_size(line: Line, quantum: float) -> float:
    weights: Counter[float] = Counter()
    for span in line.spans:
        length = len(span.text.strip())
        if length:
            weights[quantize(span.size, quantum)] += length
    if not weights:
        return 0.0
    return max(weights.items(), key=lambda item: (item[1], item[0]))[0]


def _is_bold(line: Line) -> bool:
    spans = [span for span in line.spans if span.text.strip()]
    return bool(spans) and all(span.bold for span in spans)


def make_rec(
    block_index: int,
    line: Line,
    block_width: float,
    config: StructureConfig,
    *,
    column: int | None = None,
) -> LineRec:
    x0, y0, x1, y1 = line.bbox
    width, height = x1 - x0, y1 - y0
    return LineRec(
        block_index=block_index,
        line=line,
        size=_dominant_size(line, config.line_size_quantum),
        bold=_is_bold(line),
        vertical=height > 1.5 * width > 0,
        block_width=block_width,
        column=column,
    )


def body_size(pages: Sequence[ExtractedPage], config: StructureConfig) -> float:
    """The character-weighted mode of body sizes. Falls back to all body lines when none is long enough."""
    for minimum in (config.body_stat_min_chars, 0):
        weights: Counter[float] = Counter()
        for page in pages:
            for block in page.blocks:
                if block.role != BlockRole.BODY:
                    continue
                for line in block.lines:
                    if sum(char.isalpha() for char in line.text) < minimum:
                        continue
                    for span in line.spans:
                        length = len(span.text.strip())
                        if length:
                            weights[quantize(span.size, config.line_size_quantum)] += length
        if weights:
            return max(weights.items(), key=lambda item: (item[1], item[0]))[0]
    return 0.0


def _classify(rec: LineRec, body: float, page_height: float, config: StructureConfig) -> str:
    text = rec.text
    if not text or rec.vertical:
        return "text"
    band = page_height * config.furniture_band_fraction
    if _FURNITURE.match(text) and (rec.bbox[3] <= band or rec.bbox[1] >= page_height - band):
        return "furniture"
    if _CAPTION.match(text):
        return "caption"
    if rec.size <= body - config.footnote_size_delta and rec.bbox[1] >= page_height * (1 - config.footnote_band_fraction):
        return "footnote"
    larger = rec.size >= body + config.heading_size_delta
    if _NUMBER_LABEL.match(text) and (rec.bold or larger):
        return "number"
    heading_shape = len(text) <= config.heading_max_chars and not text.endswith(_NO_HEADING_END)
    if heading_shape and (larger or (rec.bold and rec.size >= body - _BOLD_TOLERANCE_PT)):
        return "heading"
    if _BULLET_ONLY.match(text):
        return "bullet"
    if _LIST_START.match(text):
        return "list"
    return "text"


def _breaks(prev: LineRec, rec: LineRec, config: StructureConfig, *, allow_indent_break: bool) -> bool:
    """True when a new paragraph must start between two lines of one block (ARCHITECTURE §11)."""
    # PyMuPDF often splits one paragraph into several one-line blocks (arXiv corpus: 474 of the 496 body blocks on pages 1 to 10
    # held one line). Lines of one column may therefore continue across P1 blocks, and the
    # gap, short-line and indent rules below decide the break. A column change always breaks.
    if prev.block_index != rec.block_index and (prev.column is None or prev.column != rec.column):
        return True
    height = max(prev.bbox[3] - prev.bbox[1], 1e-6)
    if rec.bbox[1] - prev.bbox[3] > config.paragraph_gap_factor * height:
        return True
    prev_width = prev.bbox[2] - prev.bbox[0]
    if prev.text.endswith(_SENTENCE_END) and prev_width < config.short_line_fraction * rec.block_width:
        return True
    if allow_indent_break and rec.bbox[0] > prev.bbox[0] + 2 * prev.size and prev_width >= 0.9 * rec.block_width:
        return True
    return False


def group(recs: Sequence[LineRec], config: StructureConfig) -> list[Pending]:
    """Group the body lines of one page, in P1 order, into pending units."""
    pendings: list[Pending] = []
    current: Pending | None = None
    seen_tables: set[int] = set()
    index = 0
    while index < len(recs):
        rec = recs[index]
        index += 1
        if rec.table is not None:
            current = None
            if rec.table not in seen_tables:
                seen_tables.add(rec.table)
                pendings.append(Pending("table", table=rec.table))
            continue
        kind = rec.kind
        if kind == "furniture":
            current = None
            pendings.append(Pending("furniture", [rec]))
            continue
        if kind == "number":
            follower = recs[index] if index < len(recs) else None
            close = follower is not None and follower.bbox[1] - rec.bbox[3] <= 2.0 * max(rec.bbox[3] - rec.bbox[1], 1e-6)
            if follower is not None and close and follower.table is None and follower.kind == "heading":
                current = Pending("heading", [rec, follower])
                pendings.append(current)
                index += 1
                continue
            kind = "text"
        if kind == "heading":
            if (
                current is not None
                and current.kind == "heading"
                and current.lines[-1].block_index == rec.block_index
                and abs(current.lines[-1].size - rec.size) < _BOLD_TOLERANCE_PT
            ):
                current.lines.append(rec)
                continue
            current = Pending("heading", [rec])
            pendings.append(current)
            continue
        if kind == "bullet":
            current = Pending("list_item", [rec], open_bullet=True)
            pendings.append(current)
            continue
        if kind == "list":
            current = Pending("list_item", [rec])
            pendings.append(current)
            continue
        if kind == "caption":
            current = Pending("caption", [rec])
            pendings.append(current)
            continue
        if kind == "footnote":
            if (
                current is not None
                and current.kind == "footnote"
                and not _breaks(current.lines[-1], rec, config, allow_indent_break=False)
            ):
                current.lines.append(rec)
                continue
            if _FOOTNOTE_MARK.match(rec.text):
                current = Pending("footnote", [rec])
                pendings.append(current)
                continue
            kind = "text"
        if current is not None:
            if current.kind == "list_item" and current.open_bullet:
                current.lines.append(rec)
                current.open_bullet = False
                continue
            if current.kind == "list_item" and not _breaks(current.lines[-1], rec, config, allow_indent_break=False):
                current.lines.append(rec)
                continue
            if current.kind in {"paragraph", "caption"} and not _breaks(
                current.lines[-1], rec, config, allow_indent_break=True
            ):
                current.lines.append(rec)
                continue
        current = Pending("paragraph", [rec])
        pendings.append(current)
    return pendings


def heading_label_depth(text: str) -> int:
    """A numbered label gives its depth: ``1`` is 1, ``1.1`` is 2. Without a label the depth is 1."""
    match = _LABEL_PREFIX.match(text.strip())
    return match.group(1).count(".") + 1 if match else 1


def plan_page(
    page: ExtractedPage,
    geometry: PageGeometry | None,
    body: float,
    config: StructureConfig,
) -> PagePlan:
    """Classify, claim table cells and group the body lines of one structured page."""
    recs: list[LineRec] = []
    for block_index, block in enumerate(page.blocks):
        if block.role != BlockRole.BODY or not block.lines:
            continue
        for line in block.lines:
            recs.append(make_rec(block_index, line, 0.0, config, column=block.column_index))
    # The width used by the short-line rule is the widest body line of the line's column, not the
    # width of its own block: PyMuPDF often gives one-line blocks, whose width says nothing about the column.
    column_width: dict[int | None, float] = {}
    for rec in recs:
        width = rec.bbox[2] - rec.bbox[0]
        column_width[rec.column] = max(column_width.get(rec.column, 0.0), width)
    for rec in recs:
        rec.block_width = column_width[rec.column]

    issues: list[tuple[str, str]] = []
    tables: tuple[TableGeometry, ...] = ()
    if geometry is not None:
        if geometry.issue_code is not None:
            issues.append((geometry.issue_code, geometry.detail))
        elif geometry.tables:
            if page.rotation != 0:
                issues.append(("table_geometry_mismatch", "the page is rotated, so its table boxes are not used"))
            else:
                tables = geometry.tables

    centres = [rec.centre for rec in recs]
    cells: dict[int, dict[tuple[int, int], list[LineRec]]] = {}
    for table_index, table in enumerate(tables):
        inside = count_inside(table, centres, config.table_cell_tolerance)
        assigned = assign_cells(table, centres, config.table_cell_tolerance)
        claimed = [index for index, holder in enumerate(assigned) if holder is not None and recs[index].table is None]
        if inside >= 3 and len(claimed) / inside < config.table_min_claim_share:
            issues.append(
                (
                    "table_geometry_mismatch",
                    f"table {table_index + 1}: {len(claimed)} of {inside} text lines in the box fall in cells",
                )
            )
            continue
        cell_map: dict[tuple[int, int], list[LineRec]] = {}
        for index in claimed:
            recs[index].table = table_index
            recs[index].cell = assigned[index]
            cell_map.setdefault(assigned[index], []).append(recs[index])
        cells[table_index] = cell_map

    for rec in recs:
        if rec.table is None:
            rec.kind = _classify(rec, body, page.height, config)
    pendings = group(recs, config)
    captions = [rec for rec in recs if rec.kind == "caption" and rec.table is None]
    return PagePlan(
        pdf_page=page.pdf_page,
        recs=recs,
        pendings=pendings,
        tables=tables,
        cells=cells,
        captions=captions,
        issues=issues,
    )


def heading_size_levels(plans: Sequence[PagePlan], body: float, config: StructureConfig) -> list[float]:
    """The sizes that become heading levels, largest first.

    A size qualifies when it is at least ``heading_size_delta`` above body size and at least
    ``heading_level_min_count`` heading lines carry it.
    """
    counts: Counter[float] = Counter()
    for plan in plans:
        for pending in plan.pendings:
            if pending.kind != "heading":
                continue
            size = max(line.size for line in pending.lines)
            if size >= body + config.heading_size_delta:
                counts[quantize(size, config.line_size_quantum)] += 1
    return sorted((size for size, count in counts.items() if count >= config.heading_level_min_count), reverse=True)


def heading_level(pending: Pending, body: float, size_levels: Sequence[float], config: StructureConfig) -> int:
    """A heading in a qualifying size takes that size's rank. Any other heading follows the size levels,
    at the depth of its numbered label (``1`` is 1, ``1.1`` is 2), or at depth 1 without a label."""
    size = quantize(max(line.size for line in pending.lines), config.line_size_quantum)
    if size in size_levels:
        return size_levels.index(size) + 1
    return len(size_levels) + heading_label_depth(pending.lines[0].text)
