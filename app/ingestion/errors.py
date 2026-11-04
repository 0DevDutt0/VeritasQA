"""Ingestion errors. Every failure raised by the ingestion package is an IngestionError."""

from __future__ import annotations

from app.common.errors import VeritasQAError

# Fixed codes for PdfRejectedError. Each code names one reason a file is not accepted as a PDF.
REJECTION_CODES = frozenset(
    {
        "file_missing",
        "file_empty",
        "file_too_large",
        "bad_header",
        "cannot_open",
        "encrypted_requires_password",
        "no_pages",
    }
)


class IngestionError(VeritasQAError):
    """Base class for ingestion failures."""


class IngestionConfigError(IngestionError):
    """The ingestion configuration is missing, is not valid TOML, or fails validation."""


class PdfRejectedError(IngestionError):
    """The file is not accepted as a readable PDF. ``code`` is one of REJECTION_CODES."""

    def __init__(self, code: str, message: str) -> None:
        if code not in REJECTION_CODES:
            raise ValueError(f"unknown rejection code: {code!r}")
        super().__init__(message)
        self.code = code


class OcrError(IngestionError):
    """A tesseract run could not start, failed, timed out or produced unusable output."""


class RenderError(IngestionError):
    """A page could not be rendered, for example because the page number is out of range."""
