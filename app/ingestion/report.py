"""Writes the extraction outputs under ``<out_root>/<document_id>/`` (ARCHITECTURE §10).

The layout is extraction_report.json, pages/pNNNN.txt (the immutable raw_text of each page) and
renders/pNNNN.png (renders of non-OK pages, for inspection). Generated subfolders are cleared
before a write, so a rerun leaves no stale files behind.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from app.common import files
from app.ingestion.config import IngestionConfig
from app.ingestion.errors import IngestionError
from app.ingestion.models import ExtractedDocument, PageStatus
from app.ingestion.render import render_page_png

REPORT_NAME = "extraction_report.json"


def load_outputs(report_path: Path | str) -> ExtractedDocument:
    """Load a report written by :func:`write_outputs`, with each page's raw_text read from its file.

    The report omits raw_text, so the text is read from ``pages/pNNNN.txt`` and checked against
    ``raw_text_sha256``. A missing or changed page file raises IngestionError.
    """
    path = Path(report_path)
    base = path.parent
    data = files.read_json(path)
    for page in data["pages"]:
        relative = page.get("raw_text_path")
        if not relative:
            raise IngestionError(f"page {page.get('pdf_page')} has no raw text file in the report")
        text_path = base / relative
        if not text_path.is_file():
            raise IngestionError(f"raw text file is missing: {relative}")
        text = files.read_text(text_path)
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != page["raw_text_sha256"]:
            raise IngestionError(f"raw text file changed since the report was written: {relative}")
        page["raw_text"] = text
    return ExtractedDocument.model_validate(data)


def write_outputs(
    document: ExtractedDocument,
    pdf_path: Path,
    out_root: Path,
    config: IngestionConfig,
) -> Path:
    """Write the report, the page texts and the renders. Returns the report path."""
    base = Path(out_root) / document.document_id
    shutil.rmtree(base / "pages", ignore_errors=True)
    shutil.rmtree(base / "renders", ignore_errors=True)

    for page in document.pages:
        relative = f"pages/p{page.pdf_page:04d}.txt"
        files.write_text(base / relative, page.raw_text)
        page.raw_text_path = relative

    for page in document.pages:
        if page.status is not PageStatus.OK:
            relative = f"renders/p{page.pdf_page:04d}.png"
            render_page_png(pdf_path, page.pdf_page, config.render_dpi, base / relative)
            page.render_path = relative

    report_path = base / REPORT_NAME
    files.write_text(report_path, document.model_dump_json(indent=2) + "\n")
    return report_path
