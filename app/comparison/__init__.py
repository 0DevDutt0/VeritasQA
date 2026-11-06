"""Page-by-page comparison of an uploaded document with its earlier version (P15, ARCHITECTURE §20).

The package is pure: it takes plain records and returns plain results. The command line reads the store, calls it and
writes the report.
"""

from app.comparison.documents import (
    DocumentComparison,
    DocumentInfo,
    Selection,
    compare_documents,
    select_earlier,
)
from app.comparison.pages import PageComparison, PageDifference, PageRecord, WordChange, compare_pages
from app.comparison.report import render_report
from app.comparison.text import normalize_page_text

__all__ = [
    "DocumentComparison",
    "DocumentInfo",
    "PageComparison",
    "PageDifference",
    "PageRecord",
    "Selection",
    "WordChange",
    "compare_documents",
    "compare_pages",
    "normalize_page_text",
    "render_report",
    "select_earlier",
]
