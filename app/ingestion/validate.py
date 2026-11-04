"""File-level validation, run before any page is parsed (ARCHITECTURE §10).

The file is hashed in chunks, so large files are never read whole. PyMuPDF is opened only after the
cheap checks pass. The error messages use the file name, never the full path.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitz

from app.ingestion.config import IngestionConfig
from app.ingestion.errors import PdfRejectedError
from app.ingestion.models import PdfFileInfo

_CHUNK_BYTES = 1 << 20
_PDF_HEADER = b"%PDF-"
_EOF_MARKER = b"%%EOF"


def document_id_for(sha256_hex: str) -> str:
    """``doc-`` plus the first 16 hex characters of the file's SHA-256. Stable across renames."""
    return f"doc-{sha256_hex[:16]}"


def _hash_header_and_tail(path: Path, tail_bytes: int) -> tuple[str, bytes, bytes]:
    digest = hashlib.sha256()
    header = b""
    tail = b""
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            if not header:
                header = chunk[: len(_PDF_HEADER)]
            digest.update(chunk)
            tail = (tail + chunk)[-tail_bytes:]
    return digest.hexdigest(), header, tail


def validate_pdf(path: Path | str, config: IngestionConfig) -> PdfFileInfo:
    """Accept or reject a file as a readable PDF. Raises PdfRejectedError with a fixed code."""
    target = Path(path)
    if not target.is_file():
        raise PdfRejectedError("file_missing", f"{target.name} does not exist or is not a file")
    size = target.stat().st_size
    if size == 0:
        raise PdfRejectedError("file_empty", f"{target.name} is empty")
    if size > config.max_file_bytes:
        raise PdfRejectedError(
            "file_too_large",
            f"{target.name} is {size} bytes; the limit is {config.max_file_bytes} bytes",
        )

    sha256_hex, header, tail = _hash_header_and_tail(target, config.eof_tail_bytes)
    if header != _PDF_HEADER:
        raise PdfRejectedError("bad_header", f"{target.name} does not start with %PDF-")

    try:
        document = fitz.open(target)
    except Exception as exc:  # PyMuPDF raises several exception types for unreadable files
        raise PdfRejectedError("cannot_open", f"PyMuPDF cannot open {target.name}") from exc

    with document:
        if document.needs_pass:
            raise PdfRejectedError(
                "encrypted_requires_password",
                f"{target.name} needs a password; VeritasQA does not decrypt files",
            )
        page_count = document.page_count
        if page_count < 1:
            raise PdfRejectedError("no_pages", f"{target.name} has no pages")
        is_repaired = bool(document.is_repaired)

    return PdfFileInfo(
        source_name=target.name,
        size_bytes=size,
        sha256=sha256_hex,
        document_id=document_id_for(sha256_hex),
        page_count=page_count,
        is_repaired=is_repaired,
        has_eof_marker=_EOF_MARKER in tail,
    )
