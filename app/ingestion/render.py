"""Page rendering with PyMuPDF: PNG files for inspection, and the ink measure for blank-page checks."""

from __future__ import annotations

from pathlib import Path

import fitz

from app.ingestion.errors import RenderError

_WHITE_LEVEL = 250  # grey values at or above this count as white


def render_page_png(path: Path | str, pdf_page: int, dpi: int, out_path: Path | str) -> Path:
    """Render one page (1-based) to a PNG file and return its path."""
    if dpi <= 0:
        raise RenderError(f"render DPI must be positive, not {dpi}")
    with fitz.open(path) as document:
        if not 1 <= pdf_page <= document.page_count:
            raise RenderError(f"page {pdf_page} is outside 1..{document.page_count}")
        pixmap = document[pdf_page - 1].get_pixmap(dpi=dpi, alpha=False)
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(target)
    return target


def ink_ratio(pixmap: fitz.Pixmap) -> float:
    """Fraction of pixels darker than white in a single-channel (greyscale) pixmap."""
    if pixmap.n != 1:
        raise RenderError("ink_ratio needs a greyscale pixmap")
    samples = pixmap.samples
    if not samples:
        return 0.0
    dark = sum(1 for value in samples if value < _WHITE_LEVEL)
    return dark / len(samples)
