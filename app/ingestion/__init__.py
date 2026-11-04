"""PDF ingestion, extraction and page-level quality validation (P1). See docs/ARCHITECTURE.md §10."""

from app.ingestion.config import DEFAULT_CONFIG_PATH, IngestionConfig, load_ingestion_config
from app.ingestion.errors import (
    IngestionConfigError,
    IngestionError,
    OcrError,
    PdfRejectedError,
    RenderError,
)
from app.ingestion.extract import EXTRACTOR_VERSION, extract_document
from app.ingestion.models import (
    ExtractedDocument,
    ExtractedPage,
    PageStatus,
    PdfFileInfo,
    QualityStatus,
    quality_for,
)
from app.ingestion.ocr import ocr_page, tesseract_available
from app.ingestion.render import render_page_png
from app.ingestion.report import load_outputs
from app.ingestion.validate import validate_pdf

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "EXTRACTOR_VERSION",
    "ExtractedDocument",
    "ExtractedPage",
    "IngestionConfig",
    "IngestionConfigError",
    "IngestionError",
    "OcrError",
    "PageStatus",
    "PdfFileInfo",
    "PdfRejectedError",
    "QualityStatus",
    "RenderError",
    "extract_document",
    "load_ingestion_config",
    "load_outputs",
    "ocr_page",
    "quality_for",
    "render_page_png",
    "tesseract_available",
    "validate_pdf",
]
