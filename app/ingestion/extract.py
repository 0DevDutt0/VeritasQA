"""PDF extraction (P1): PyMuPDF text and layout, pdfplumber table detection, classification and OCR.

The extractor reads one open document in three steps:
1. scan every page: text lines, invisible-text counts, image coverage and, for text-free pages, ink;
2. find the headers and footers that repeat across pages, then order the body lines of each page;
3. assemble raw_text, classify each page, run OCR on image-only pages when it is available, and
   stamp the document-level issues onto every page.

Lines are the ordering unit. Consecutive lines that share a PyMuPDF block, a column and a band form
one block. The result is an ExtractedDocument. Nothing is written unless ``out_root`` is given.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import fitz
import pdfplumber

from app.ingestion import layout, ocr, render
from app.ingestion.config import IngestionConfig, config_fingerprint, load_ingestion_config
from app.ingestion.errors import OcrError
from app.ingestion.models import (
    Block,
    BlockRole,
    Box,
    ExtractedDocument,
    ExtractedPage,
    ExtractionMethod,
    Issue,
    Line,
    PageStatus,
    ReadingOrder,
    Span,
    quality_for,
)
from app.ingestion.quality import PageFeatures, classify_page, text_profile
from app.ingestion.report import write_outputs
from app.ingestion.validate import validate_pdf

EXTRACTOR_VERSION = "p1-ingestion-2"
logger = logging.getLogger(__name__)

_TEXT_FLAGS = (
    fitz.TEXT_PRESERVE_IMAGES
    | fitz.TEXT_PRESERVE_LIGATURES
    | fitz.TEXT_PRESERVE_WHITESPACE
    | fitz.TEXT_MEDIABOX_CLIP
)
_BOLD_FLAG = 16
_INVISIBLE_RENDER_MODES = frozenset({3, 7})
_LINE_SEPARATOR = "\n"
_BLOCK_SEPARATOR = "\n\n"
_MESSAGE_LIMIT = 300
_OCR_BLOCK_NO = -1

OcrRunner = Callable[[Path], str]


@dataclass
class _DraftLine:
    block_no: int
    bbox: Box
    text: str
    spans: list[Span]
    raw_start: int = 0
    raw_end: int = 0
    hidden_chars: int = 0


@dataclass
class _DraftBlock:
    block_no: int
    role: BlockRole
    bbox: Box
    lines: list[_DraftLine] = field(default_factory=list)
    reading_index: int | None = None
    column_index: int | None = None
    raw_start: int | None = None
    raw_end: int | None = None


@dataclass
class _PageScan:
    index: int
    width: float
    height: float
    rotation: int
    printed_page: str | None
    text_lines: list[_DraftLine]
    image_blocks: list[_DraftBlock]
    image_coverage: float
    visible_chars: int | None
    hidden_chars: int | None
    ink_ratio: float | None


def _union(boxes: Sequence[Box]) -> Box:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _span_model(span: dict) -> Span:
    flags = int(span["flags"])
    return Span(
        text=span["text"],
        bbox=tuple(span["bbox"]),
        font=span["font"],
        size=float(span["size"]),
        flags=flags,
        bold=bool(flags & _BOLD_FLAG),
    )


def _line_segments(line: dict, gap_em: float, block_no: int) -> list[_DraftLine]:
    """Split one PyMuPDF line wherever neighbouring spans are more than ``gap_em`` font sizes apart.

    The split applies in both directions. PyMuPDF can list the spans of two columns in one line,
    and the second column then starts to the left of the first.
    """
    groups: list[list[dict]] = []
    previous: dict | None = None
    for span in line["spans"]:
        if previous is None or abs(span["bbox"][0] - previous["bbox"][2]) > gap_em * previous["size"]:
            groups.append([])
        groups[-1].append(span)
        previous = span
    segments: list[_DraftLine] = []
    for group in groups:
        text = "".join(span["text"] for span in group)
        if not text.strip():
            continue
        segments.append(
            _DraftLine(
                block_no=block_no,
                bbox=_union([tuple(span["bbox"]) for span in group]),
                text=text,
                spans=[_span_model(span) for span in group],
            )
        )
    return segments


def _image_coverage(page: fitz.Page, images: Sequence[_DraftBlock]) -> float:
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return 0.0
    covered = 0.0
    for image in images:
        clipped = fitz.Rect(image.bbox) & page.rect
        covered += max(0.0, clipped.width) * max(0.0, clipped.height)
    return min(1.0, covered / page_area)


def _render_mode_counts(page: fitz.Page) -> tuple[int | None, int | None, list[tuple[float, float]]]:
    """Count visible and invisible characters, and return the centre of each invisible glyph.

    Returns (None, None, []) when the trace cannot be read. A trace character is
    (unicode, glyph, origin, bbox, ...), so index 3 is the glyph bounding box.
    """
    try:
        traces = page.get_texttrace()
    except Exception:  # noqa: BLE001 - the classifier reports the unknown state as an issue
        logger.debug("text render mode unavailable on page %s", page.number + 1)
        return None, None, []
    visible = hidden = 0
    hidden_centres: list[tuple[float, float]] = []
    for trace in traces:
        characters = trace.get("chars", ())
        if trace.get("type") in _INVISIBLE_RENDER_MODES:
            hidden += len(characters)
            for character in characters:
                x0, y0, x1, y1 = character[3]
                hidden_centres.append(((x0 + x1) / 2, (y0 + y1) / 2))
        else:
            visible += len(characters)
    return visible, hidden, hidden_centres


def _scan_page(document: fitz.Document, index: int, config: IngestionConfig) -> _PageScan:
    page = document[index]
    page_dict = page.get_text("dict", flags=_TEXT_FLAGS)
    text_lines: list[_DraftLine] = []
    image_blocks: list[_DraftBlock] = []
    for block_no, block in enumerate(page_dict["blocks"]):
        if block["type"] == 1:
            image_blocks.append(_DraftBlock(block_no=block_no, role=BlockRole.IMAGE, bbox=tuple(block["bbox"])))
        elif block["type"] == 0:
            for line in block["lines"]:
                text_lines.extend(_line_segments(line, config.line_gap_em, block_no))
    visible, hidden, hidden_centres = _render_mode_counts(page)
    for centre_x, centre_y in hidden_centres:
        for line in text_lines:
            x0, y0, x1, y1 = line.bbox
            if x0 - 1.0 <= centre_x <= x1 + 1.0 and y0 - 1.0 <= centre_y <= y1 + 1.0:
                line.hidden_chars += 1
                break
    ink: float | None = None
    if not text_lines:
        pixmap = page.get_pixmap(dpi=config.blank_check_dpi, colorspace=fitz.csGRAY, alpha=False)
        ink = render.ink_ratio(pixmap)
    return _PageScan(
        index=index,
        width=float(page.rect.width),
        height=float(page.rect.height),
        rotation=int(page.rotation),
        printed_page=page.get_label() or None,
        text_lines=text_lines,
        image_blocks=image_blocks,
        image_coverage=_image_coverage(page, image_blocks),
        visible_chars=visible,
        hidden_chars=hidden,
        ink_ratio=ink,
    )


def _detect_tables(path: Path, page_count: int) -> tuple[list[int | None], list[str | None]]:
    """Count ruled tables per page with pdfplumber (lines strategy). Failures are reported per page."""
    counts: list[int | None] = [None] * page_count
    errors: list[str | None] = [None] * page_count
    try:
        plumber = pdfplumber.open(path)
    except Exception as exc:  # noqa: BLE001
        message = f"pdfplumber could not open the file ({type(exc).__name__})"
        return counts, [message] * page_count
    with plumber:
        pages = plumber.pages
        for index in range(page_count):
            if index >= len(pages):
                errors[index] = "pdfplumber found fewer pages than PyMuPDF"
                continue
            try:
                counts[index] = len(pages[index].find_tables())
            except Exception as exc:  # noqa: BLE001
                errors[index] = f"pdfplumber failed on this page ({type(exc).__name__})"
    return counts, errors


def _ocr_setup(config: IngestionConfig, ocr_command: Sequence[str] | None) -> tuple[OcrRunner | None, str]:
    """Return the OCR runner (or None) and the state: enabled, disabled or unavailable."""
    if ocr_command is not None:
        command = tuple(ocr_command)

        def run_explicit(image: Path) -> str:
            return ocr.ocr_page(
                image,
                language=config.ocr_language,
                timeout_seconds=config.ocr_timeout_seconds,
                command=command,
            )

        return run_explicit, "enabled"
    if config.ocr_mode == "off":
        return None, "disabled"
    if not ocr.tesseract_available():
        return None, "unavailable"

    def run_path(image: Path) -> str:
        return ocr.ocr_page(
            image,
            language=config.ocr_language,
            timeout_seconds=config.ocr_timeout_seconds,
            command=None,
        )

    return run_path, "enabled"


def _reblock(
    sequence: Sequence[tuple[_DraftLine, int | None, int]],
    role: BlockRole,
) -> list[_DraftBlock]:
    """Group consecutive lines that share a PyMuPDF block, a column and a band into one block."""
    blocks: list[_DraftBlock] = []
    last_key: tuple[int, int | None, int] | None = None
    for line, column, band in sequence:
        key = (line.block_no, column, band)
        if blocks and key == last_key:
            blocks[-1].lines.append(line)
            blocks[-1].bbox = _union([blocks[-1].bbox, line.bbox])
        else:
            blocks.append(
                _DraftBlock(
                    block_no=line.block_no,
                    role=role,
                    bbox=line.bbox,
                    lines=[line],
                    column_index=column,
                )
            )
        last_key = key
    return blocks


def _assemble(blocks: Sequence[_DraftBlock]) -> str:
    """Join the text blocks into raw_text and record each block's and line's offsets in it."""
    parts: list[str] = []
    offset = 0
    for position, block in enumerate(blocks):
        if position:
            parts.append(_BLOCK_SEPARATOR)
            offset += len(_BLOCK_SEPARATOR)
        block.raw_start = offset
        for line_index, line in enumerate(block.lines):
            if line_index:
                parts.append(_LINE_SEPARATOR)
                offset += len(_LINE_SEPARATOR)
            line.raw_start = offset
            parts.append(line.text)
            offset += len(line.text)
            line.raw_end = offset
        block.raw_end = offset
    return "".join(parts)


def _block_model(block: _DraftBlock) -> Block:
    return Block(
        block_no=block.block_no,
        role=block.role,
        bbox=block.bbox,
        reading_index=block.reading_index,
        column_index=block.column_index,
        raw_start=block.raw_start,
        raw_end=block.raw_end,
        lines=[
            Line(
                raw_start=line.raw_start,
                raw_end=line.raw_end,
                bbox=line.bbox,
                text=line.text,
                spans=line.spans,
                hidden_chars=line.hidden_chars,
            )
            for line in block.lines
        ],
    )


def _ocr_block(text: str, scan: _PageScan) -> _DraftBlock:
    page_box: Box = (0.0, 0.0, scan.width, scan.height)
    lines = [
        _DraftLine(block_no=_OCR_BLOCK_NO, bbox=page_box, text=line, spans=[])
        for line in text.split(_LINE_SEPARATOR)
        if line.strip()
    ]
    return _DraftBlock(
        block_no=_OCR_BLOCK_NO,
        role=BlockRole.OCR,
        bbox=page_box,
        lines=lines,
        reading_index=0,
    )


def _render_for_ocr(document: fitz.Document, index: int, dpi: int, workdir: Path) -> Path:
    target = workdir / f"page-{index + 1:04d}.png"
    document[index].get_pixmap(dpi=dpi, alpha=False).save(target)
    return target


def _build_page(
    document: fitz.Document,
    scan: _PageScan,
    page_roles: dict[int, str],
    config: IngestionConfig,
    runner: OcrRunner | None,
    ocr_state: str,
    workdir: Path,
    rules: layout.LayoutRules,
    table_count: int | None,
    table_error: str | None,
) -> ExtractedPage:
    line_boxes = [
        layout.TextBox(key=position, box=line.bbox, text=line.text)
        for position, line in enumerate(scan.text_lines)
    ]
    body_boxes = [box for box in line_boxes if box.key not in page_roles]
    order = layout.reading_order(body_boxes, rules)

    header_lines = sorted(
        (scan.text_lines[key] for key, role in page_roles.items() if role == "header"),
        key=lambda line: (line.bbox[1], line.bbox[0]),
    )
    footer_lines = sorted(
        (scan.text_lines[key] for key, role in page_roles.items() if role == "footer"),
        key=lambda line: (line.bbox[1], line.bbox[0]),
    )
    headers = _reblock([(line, None, 0) for line in header_lines], BlockRole.HEADER)
    footers = _reblock([(line, None, 0) for line in footer_lines], BlockRole.FOOTER)
    body_sequence = [
        (scan.text_lines[key], column, band)
        for (key, column), band in zip(order.order, order.bands)
    ]
    bodies = _reblock(body_sequence, BlockRole.BODY)
    ordered = headers + bodies + footers

    raw = _assemble(ordered)
    profile = text_profile(raw)
    status, issues = classify_page(
        PageFeatures(
            text=profile,
            image_coverage=scan.image_coverage,
            ink_ratio=scan.ink_ratio,
            visible_chars=scan.visible_chars,
            hidden_chars=scan.hidden_chars,
            table_count=table_count,
            table_error=table_error,
            rotation=scan.rotation,
            reading_uncertain=order.uncertain_reasons,
        ),
        config,
    )
    method = ExtractionMethod.NATIVE_TEXT if profile.non_space_chars else ExtractionMethod.NONE
    reading = ReadingOrder(order.method)
    column_count = order.column_count
    uncertain = bool(order.uncertain_reasons)

    if status is PageStatus.SCANNED:
        if runner is not None:
            try:
                text = runner(_render_for_ocr(document, scan.index, config.ocr_dpi, workdir))
            except OcrError as exc:
                issues.append(Issue(code="ocr_failed", severity="warning", detail=str(exc)))
            else:
                if text:
                    ocr_block = _ocr_block(text, scan)
                    ordered = [ocr_block]
                    raw = _assemble(ordered)
                    profile = text_profile(raw)
                    status = PageStatus.OCR_TEXT
                    method = ExtractionMethod.OCR_TESSERACT
                    reading = ReadingOrder.NONE
                    column_count = 0
                    uncertain = False
                    issues.append(
                        Issue(
                            code="ocr_text_unverified",
                            severity="warning",
                            detail="text produced by tesseract; OCR text is unverified and its order is tesseract's",
                        )
                    )
                else:
                    issues.append(Issue(code="ocr_no_text", severity="warning", detail="tesseract returned no text"))
        elif ocr_state == "disabled":
            issues.append(Issue(code="ocr_disabled", severity="info", detail='OCR is off (ocr_mode = "off")'))
        else:
            issues.append(
                Issue(code="ocr_unavailable", severity="warning", detail="tesseract is not on PATH; the page needs OCR")
            )

    for reading_index, block in enumerate(ordered):
        block.reading_index = reading_index
    images = sorted(scan.image_blocks, key=lambda block: (block.bbox[1], block.bbox[0]))
    blocks = [_block_model(block) for block in ordered] + [_block_model(block) for block in images]

    return ExtractedPage(
        pdf_page=scan.index + 1,
        printed_page=scan.printed_page,
        width=scan.width,
        height=scan.height,
        rotation=scan.rotation,
        status=status,
        quality_status=quality_for(status),
        extraction_method=method,
        visible_chars=scan.visible_chars,
        hidden_chars=scan.hidden_chars,
        non_space_chars=profile.non_space_chars,
        image_coverage=scan.image_coverage,
        ink_ratio=scan.ink_ratio,
        table_count=table_count,
        column_count=column_count,
        reading_order=reading,
        reading_order_uncertain=uncertain,
        issues=issues,
        blocks=blocks,
        raw_text=raw,
        raw_text_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def _short_message(messages: str) -> str:
    collapsed = " | ".join(line.strip() for line in messages.splitlines() if line.strip())
    return collapsed[:_MESSAGE_LIMIT]


def _stamp_document_issues(pages: Sequence[ExtractedPage], document_issues: Sequence[Issue]) -> None:
    """Repeat each document-level warning on every page, so per-page gates see it (ARCHITECTURE §10)."""
    stamped = [issue for issue in document_issues if issue.severity == "warning"]
    for page in pages:
        for issue in stamped:
            page.issues.append(
                Issue(code=issue.code, severity="warning", detail=f"document level: {issue.detail}")
            )
        if stamped and page.status is PageStatus.OK:
            page.status = PageStatus.WARNING
            page.quality_status = quality_for(page.status)


def extract_document(
    path: Path | str,
    *,
    config: IngestionConfig | None = None,
    out_root: Path | str | None = None,
    ocr_command: Sequence[str] | None = None,
) -> ExtractedDocument:
    """Validate, extract and classify one PDF.

    ``out_root`` writes the report, the page texts and the renders under ``out_root/<document_id>/``.
    ``ocr_command`` replaces the tesseract executable (tests use a stub). Raises PdfRejectedError
    when the file is not accepted.
    """
    settings = config if config is not None else load_ingestion_config()
    pdf_path = Path(path)
    info = validate_pdf(pdf_path, settings)
    table_counts, table_errors = _detect_tables(pdf_path, info.page_count)
    runner, ocr_state = _ocr_setup(settings, ocr_command)
    rules = layout.LayoutRules(
        wide_block_width_fraction=settings.wide_block_width_fraction,
        min_gutter_fraction=settings.min_gutter_fraction,
        overlap_area_fraction_max=settings.overlap_area_fraction_max,
    )

    fitz.TOOLS.reset_mupdf_warnings()
    with fitz.open(pdf_path) as document, tempfile.TemporaryDirectory() as scratch:
        scans = [_scan_page(document, index, settings) for index in range(document.page_count)]
        margin_roles = layout.find_repeated_margins(
            [
                [layout.TextBox(key=position, box=line.bbox, text=line.text) for position, line in enumerate(scan.text_lines)]
                for scan in scans
            ],
            [scan.height for scan in scans],
            band_fraction=settings.header_footer_band_fraction,
            min_pages=settings.header_footer_min_pages,
        )
        roles_by_page: dict[int, dict[int, str]] = defaultdict(dict)
        for (page_index, unit_key), role in margin_roles.items():
            roles_by_page[page_index][unit_key] = role
        pages = [
            _build_page(
                document,
                scan,
                roles_by_page.get(scan.index, {}),
                settings,
                runner,
                ocr_state,
                Path(scratch),
                rules,
                table_counts[scan.index],
                table_errors[scan.index],
            )
            for scan in scans
        ]
        messages = _short_message(fitz.TOOLS.mupdf_warnings())

    document_issues: list[Issue] = []
    if info.is_repaired:
        detail = "MuPDF repaired the file"
        document_issues.append(
            Issue(code="pdf_repaired", severity="warning", detail=f"{detail}: {messages}" if messages else detail)
        )
    if not info.has_eof_marker:
        document_issues.append(
            Issue(
                code="pdf_missing_eof",
                severity="warning",
                detail=f"no %%EOF marker in the last {settings.eof_tail_bytes} bytes; the file may be truncated",
            )
        )
    if messages and not info.is_repaired:
        document_issues.append(Issue(code="mupdf_messages", severity="info", detail=messages))
    _stamp_document_issues(pages, document_issues)

    counts = Counter(page.status.value for page in pages)
    report = ExtractedDocument(
        extractor_version=EXTRACTOR_VERSION,
        pymupdf_version=fitz.VersionBind,
        pdfplumber_version=pdfplumber.__version__,
        config_sha256=config_fingerprint(settings),
        document_id=info.document_id,
        source_name=info.source_name,
        size_bytes=info.size_bytes,
        sha256=info.sha256,
        page_count=info.page_count,
        status_counts={key: counts[key] for key in sorted(counts)},
        issues=document_issues,
        pages=pages,
    )
    if out_root is not None:
        write_outputs(report, pdf_path, Path(out_root), settings)
    return report
