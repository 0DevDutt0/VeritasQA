"""Synthetic PDFs for the P2 tests.

Every file here is generated at test time with PyMuPDF and is labelled synthetic. Its text is written
by the tests, so the expected structure is known in advance. None of these files is a real document.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from tests.fixtures.synthetic_pdfs import PAGE_HEIGHT, PAGE_WIDTH

RUNNING_HEADER = "Risk Assessment Guide"
TABLE_CAPTION = "Table 1. Likelihood scale"
FOOTNOTE_TEXT = "1 This footnote explains the scale."
INTRO_TEXT = "The guide covers:"
BULLETS = ["- Assets", "- Threats", "- Controls"]
TABLE_ROWS = [["Level", "Rating", "Meaning"], ["Low", "1", "Rare"], ["High", "5", "Likely"]]
PARAGRAPH = (
    "This guide describes a structured method for assessing risk in an information system. "
    "It applies to every system that stores agency data and is written for the people who run those systems."
)


def _save(document: fitz.Document, path: Path) -> Path:
    document.save(path)
    document.close()
    return path


def _new_page(document: fitz.Document) -> fitz.Page:
    return document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)


def _running_header(page: fitz.Page) -> None:
    page.insert_text((72, 40), RUNNING_HEADER, fontsize=8)


def _ruled_table(page: fitz.Page, top: float) -> None:
    column_width, row_height = 133.33, 25
    for row in range(len(TABLE_ROWS) + 1):
        page.draw_line((72, top + row * row_height), (472, top + row * row_height))
    for column in range(4):
        page.draw_line((72 + column * column_width, top), (72 + column * column_width, top + len(TABLE_ROWS) * row_height))
    for row_index, row in enumerate(TABLE_ROWS):
        for column_index, value in enumerate(row):
            page.insert_text((72 + column_index * column_width + 5, top + row_index * row_height + 17), value, fontsize=10)


def structure_pdf(path: Path) -> Path:
    """Synthetic: two pages with two headings at 16 pt and two at 13 pt (bold), a wrapped paragraph,
    a list with an intro line, a captioned 3 x 3 ruled table, a footnote, a running header and page numbers."""
    document = fitz.open()
    page = _new_page(document)
    _running_header(page)
    page.insert_text((72, 90), "Risk Assessment Guide Overview", fontsize=16, fontname="hebo")
    page.insert_textbox(fitz.Rect(72, 105, 523, 200), PARAGRAPH, fontsize=10)
    page.insert_text((72, 230), "1 Purpose", fontsize=13, fontname="hebo")
    page.insert_text((72, 255), "The purpose of the method is to find and rank risks before they cause harm.", fontsize=10)
    page.insert_text((72, 320), "2 Scope", fontsize=13, fontname="hebo")
    page.insert_text((72, 345), INTRO_TEXT, fontsize=10)
    for offset, bullet in enumerate(BULLETS):
        page.insert_text((90, 363 + offset * 14), bullet, fontsize=10)
    page.insert_text((72, 470), TABLE_CAPTION, fontsize=10)
    _ruled_table(page, top=480)
    page.insert_text((72, 760), FOOTNOTE_TEXT, fontsize=7)
    page.insert_text((300, 820), "1", fontsize=9)

    second = _new_page(document)
    _running_header(second)
    second.insert_text((72, 90), "3 Method", fontsize=16, fontname="hebo")
    second.insert_textbox(fitz.Rect(72, 105, 523, 200), PARAGRAPH, fontsize=10)
    second.insert_text((300, 820), "2", fontsize=9)
    return _save(document, path)


def two_heading_sizes_pdf(path: Path) -> Path:
    """Synthetic: a single page with one heading at 18 pt and body text, so no size qualifies as a level."""
    document = fitz.open()
    page = _new_page(document)
    page.insert_text((72, 90), "Single Title Line", fontsize=18, fontname="hebo")
    page.insert_textbox(fitz.Rect(72, 105, 523, 200), PARAGRAPH, fontsize=10)
    return _save(document, path)
