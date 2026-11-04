"""Synthetic PDFs for the P1 tests.

Every file here is generated at test time with PyMuPDF and is labelled synthetic. None of them is
the owner's document, so no result computed from them describes that document (SPEC §11).
"""

from __future__ import annotations

from pathlib import Path

import fitz

PAGE_WIDTH = 595
PAGE_HEIGHT = 842

_LEFT_TEXT = "Left column sentence one. The limit is 3.5 percent. " * 3
_RIGHT_TEXT = "Right column sentence two. Permanent staff get 10 days. " * 3


def _save(document: fitz.Document, path: Path) -> Path:
    document.save(path)
    document.close()
    return path


def _new_page(document: fitz.Document) -> fitz.Page:
    return document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)


def _image_png() -> bytes:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 500), 0)
    pixmap.set_rect(pixmap.irect, (120, 120, 200))
    return pixmap.tobytes("png")


def policy_pdf(path: Path, *, pages: int = 4) -> Path:
    """Synthetic: one body paragraph per page, with a running header and a 'Page n of N' footer."""
    document = fitz.open()
    for number in range(1, pages + 1):
        page = _new_page(document)
        page.insert_text((72, 40), "ACME Policy Manual", fontsize=9)
        page.insert_textbox(
            fitz.Rect(72, 110, 523, 300),
            f"Section {number}. The limit for contract staff is 3.5 percent of payroll.",
            fontsize=11,
        )
        page.insert_text((72, 820), f"Page {number} of {pages}", fontsize=8)
    return _save(document, path)


def two_column_pdf(path: Path, *, right_first: bool = False) -> Path:
    """Synthetic: a two-column page. ``right_first`` draws the right column first in the content stream."""
    document = fitz.open()
    page = _new_page(document)
    left = fitz.Rect(60, 130, 290, 420)
    right = fitz.Rect(305, 130, 535, 420)
    pieces = [(right, _RIGHT_TEXT), (left, _LEFT_TEXT)] if right_first else [(left, _LEFT_TEXT), (right, _RIGHT_TEXT)]
    for rect, text in pieces:
        page.insert_textbox(rect, text, fontsize=10)
    return _save(document, path)


def margin_columns_pdf(path: Path, *, pages: int = 4) -> Path:
    """Synthetic: two columns on every page, with a running header and a 'Page n of N' footer."""
    document = fitz.open()
    for number in range(1, pages + 1):
        page = _new_page(document)
        page.insert_text((72, 40), "ACME Policy Manual", fontsize=9)
        page.insert_textbox(fitz.Rect(60, 110, 290, 760), _LEFT_TEXT, fontsize=10)
        page.insert_textbox(fitz.Rect(305, 110, 535, 760), _RIGHT_TEXT, fontsize=10)
        page.insert_text((72, 820), f"Page {number} of {pages}", fontsize=8)
    return _save(document, path)


def banded_columns_pdf(path: Path, *, right_first: bool = False) -> Path:
    """Synthetic: two column sections separated by a full-width heading.

    The insertion order is reversed when ``right_first`` is true, so the native order differs
    from the visual order.
    """
    document = fitz.open()
    page = _new_page(document)
    pieces = [
        (fitz.Rect(60, 110, 290, 250), "Top left text. " * 6),
        (fitz.Rect(305, 110, 535, 250), "Top right text. " * 6),
        (
            fitz.Rect(60, 262, 535, 300),
            "2. Scope of the policy. This section applies to every employee of every subsidiary "
            "in every region of the company, including contract staff and temporary workers.",
        ),
        (fitz.Rect(60, 340, 290, 480), "Bottom left text. " * 6),
        (fitz.Rect(305, 340, 535, 480), "Bottom right text. " * 6),
    ]
    if right_first:
        pieces = list(reversed(pieces))
    for rect, text in pieces:
        page.insert_textbox(rect, text, fontsize=11 if rect.width > 400 else 10)
    return _save(document, path)


def ragged_column_pdf(path: Path) -> Path:
    """Synthetic: one column of paragraphs with different widths, all starting at the same margin."""
    document = fitz.open()
    page = _new_page(document)
    page.insert_textbox(fitz.Rect(72, 100, 400, 150), "First paragraph, a wide block of text in one column. " * 2, fontsize=10)
    page.insert_textbox(fitz.Rect(72, 170, 520, 220), "Second paragraph, the widest block of the page in one column. " * 2, fontsize=10)
    page.insert_textbox(fitz.Rect(72, 240, 300, 290), "Third paragraph, narrow, in the same column. " * 2, fontsize=10)
    return _save(document, path)


def ruled_table_pdf(path: Path) -> Path:
    """Synthetic: a caption and a 3 x 3 ruled table whose cells contain 3.5 and 2.0."""
    document = fitz.open()
    page = _new_page(document)
    page.insert_text((72, 80), "Table 1. Leave limits", fontsize=10)
    top = 100
    column_width = 133.33
    row_height = 25
    for row in range(4):
        page.draw_line((72, top + row * row_height), (472, top + row * row_height))
    for column in range(4):
        page.draw_line((72 + column * column_width, top), (72 + column * column_width, top + 3 * row_height))
    rows = [["Grade", "Limit", "Notes"], ["A", "3.5", "contract"], ["B", "2.0", "temporary"]]
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            page.insert_text(
                (72 + column_index * column_width + 5, top + row_index * row_height + 17),
                value,
                fontsize=10,
            )
    return _save(document, path)


def image_only_pdf(path: Path) -> Path:
    """Synthetic: one page that is a single full-page image and has no text (a scan)."""
    document = fitz.open()
    page = _new_page(document)
    page.insert_image(fitz.Rect(50, 50, 545, 792), stream=_image_png())
    return _save(document, path)


def blank_pdf(path: Path) -> Path:
    """Synthetic: one page with nothing on it."""
    document = fitz.open()
    _new_page(document)
    return _save(document, path)


def scanned_with_text_pdf(path: Path, *, hidden: bool) -> Path:
    """Synthetic: a full-page image with a text layer. ``hidden`` makes the text invisible (render mode 3)."""
    document = fitz.open()
    page = _new_page(document)
    page.insert_image(fitz.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT), stream=_image_png())
    text = "Hidden OCR words here" if hidden else "Visible words here"
    page.insert_text((72, 100), text, fontsize=12, render_mode=3 if hidden else 0)
    return _save(document, path)


def hidden_only_pdf(path: Path) -> Path:
    """Synthetic: text that is only drawn invisibly, with no image."""
    document = fitz.open()
    page = _new_page(document)
    page.insert_text((72, 100), "Invisible words only on this page", fontsize=12, render_mode=3)
    return _save(document, path)


def hidden_beside_visible_pdf(path: Path) -> Path:
    """Synthetic: a visible paragraph with one short invisible word, and no image.

    The invisible share is well under the 2% limit, so the page is a WARNING, not a suspicious page.
    """
    document = fitz.open()
    page = _new_page(document)
    page.insert_textbox(
        fitz.Rect(72, 100, 523, 300),
        "Visible words make up the body of this page. " * 12,
        fontsize=11,
    )
    page.insert_text((72, 400), "hidden", fontsize=11, render_mode=3)
    return _save(document, path)


def hidden_paragraph_pdf(path: Path) -> Path:
    """Synthetic: a long invisible paragraph with one short visible line (for example a stamped number).

    No image is present, so only the invisible-share rule applies. The invisible text is most of the page.
    """
    document = fitz.open()
    page = _new_page(document)
    page.insert_textbox(
        fitz.Rect(72, 100, 523, 400),
        "An invisible paragraph that a reader cannot see but a text extractor still returns. " * 6,
        fontsize=10,
        render_mode=3,
    )
    page.insert_text((72, 820), "Stamp 17", fontsize=8)
    return _save(document, path)


def garbled_pdf(path: Path) -> Path:
    """Synthetic: a short sentence followed by byte codes that the base-14 font cannot map.

    The codes are appended to the page's content stream directly. PyMuPDF returns such codes as
    control characters, which is how a broken font encoding usually appears.
    """
    document = fitz.open()
    page = _new_page(document)
    page.insert_text((72, 100), "Clean words here.", fontsize=10)
    font_name = page.get_fonts()[0][4]
    codes = "".join(f"{byte:02x}" for byte in range(1, 9)) * 6
    contents = page.get_contents()[0]
    extra = f"BT /{font_name} 10 Tf 72 130 Td <{codes}> Tj ET\n".encode("ascii")
    document.update_stream(contents, document.xref_stream(contents) + extra)
    return _save(document, path)


def suspicious_pdf(path: Path) -> Path:
    """Synthetic: a sentence with every letter separated by a space (broken character spacing)."""
    document = fitz.open()
    page = _new_page(document)
    sentence = "the quick brown fox jumps over the lazy dog"
    spaced = "   ".join(" ".join(word) for word in sentence.split())
    page.insert_text((72, 100), spaced, fontsize=10)
    return _save(document, path)


def rotated_pdf(path: Path) -> Path:
    """Synthetic: an ordinary text page with a 90-degree rotation."""
    document = fitz.open()
    page = _new_page(document)
    page.insert_text((72, 100), "A rotated page with ordinary words in it.", fontsize=12)
    page.set_rotation(90)
    return _save(document, path)


def labelled_pdf(path: Path) -> Path:
    """Synthetic: three pages. The first two carry roman printed labels, and the third restarts at 1."""
    document = fitz.open()
    for number in range(3):
        page = _new_page(document)
        page.insert_text((72, 100), f"Body text on physical page {number + 1}.", fontsize=11)
    document.set_page_labels(
        [
            {"startpage": 0, "style": "r", "firstpagenum": 1},
            {"startpage": 2, "style": "D", "firstpagenum": 1},
        ]
    )
    return _save(document, path)


UNICODE_LINE = "Café — Müller à la carte €100 ±5"
UNICODE_CJK = "東京"


def unicode_pdf(path: Path) -> Path:
    """Synthetic: accented Latin letters, an em dash, a euro sign, a plus-minus sign and CJK characters.

    The base-14 fonts cannot draw the em dash or the euro sign. PyMuPDF substitutes other characters
    for them. The embedded 'china-s' font draws these characters, but it silently drops some Latin
    letters (for example ö, ñ, ß and ï) when text is inserted. The line therefore uses only letters
    that the font keeps.
    """
    document = fitz.open()
    page = _new_page(document)
    page.insert_text((72, 100), UNICODE_LINE, fontname="china-s", fontsize=12)
    page.insert_text((72, 130), UNICODE_CJK, fontname="china-s", fontsize=12)
    return _save(document, path)


def repeated_margin_pdf(path: Path, *, pages: int = 4) -> Path:
    """Synthetic: a running header and footer, plus one unique heading at the top of page 1."""
    document = fitz.open()
    for number in range(1, pages + 1):
        page = _new_page(document)
        page.insert_text((72, 40), "ACME Policy Manual", fontsize=9)
        if number == 1:
            page.insert_text((72, 70), "Unique opening heading", fontsize=12)
        page.insert_textbox(
            fitz.Rect(72, 110, 523, 300),
            f"Body paragraph number {number} with ordinary words in it.",
            fontsize=11,
        )
        page.insert_text((72, 820), f"Page {number} of {pages}", fontsize=8)
    return _save(document, path)


def encrypted_pdf(path: Path, source: Path) -> Path:
    """Synthetic: the source file encrypted with a user password, so it cannot be opened without one."""
    document = fitz.open(source)
    document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner-secret", user_pw="user-secret")
    document.close()
    return path


def truncated_pdf(path: Path, source: Path) -> Path:
    """Synthetic: the first half of the source bytes, so the end-of-file marker is missing."""
    data = source.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    return path


def junk_pdf(path: Path) -> Path:
    """Synthetic: a file that starts with the PDF header and then contains no PDF structure."""
    path.write_bytes(b"%PDF-1.4\nthis is not a pdf at all\n")
    return path
