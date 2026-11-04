"""P1 exit criteria (extraction, end to end): synthetic PDFs through PyMuPDF and pdfplumber.

Every PDF is generated at test time and labelled synthetic. Run:
pytest tests/integration/test_p1_extraction.py -q
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.ingestion import ocr
from app.ingestion.config import load_ingestion_config
from app.ingestion.errors import PdfRejectedError
from app.ingestion.extract import extract_document
from app.ingestion.models import ISSUE_CODES, BlockRole, ExtractionMethod, PageStatus, QualityStatus, ReadingOrder
from tests.fixtures import synthetic_pdfs as pdfs


@pytest.fixture
def config():
    return load_ingestion_config()


def _codes(page) -> set[str]:
    return {issue.code for issue in page.issues}


def _all_fixtures(tmp_path) -> dict[str, object]:
    source = pdfs.policy_pdf(tmp_path / "policy-source.pdf")
    return {
        "policy": pdfs.policy_pdf(tmp_path / "policy.pdf"),
        "two_column": pdfs.two_column_pdf(tmp_path / "two-column.pdf", right_first=True),
        "banded": pdfs.banded_columns_pdf(tmp_path / "banded.pdf", right_first=True),
        "ragged": pdfs.ragged_column_pdf(tmp_path / "ragged.pdf"),
        "table": pdfs.ruled_table_pdf(tmp_path / "table.pdf"),
        "image_only": pdfs.image_only_pdf(tmp_path / "image-only.pdf"),
        "blank": pdfs.blank_pdf(tmp_path / "blank.pdf"),
        "hidden_layer": pdfs.scanned_with_text_pdf(tmp_path / "hidden-layer.pdf", hidden=True),
        "visible_layer": pdfs.scanned_with_text_pdf(tmp_path / "visible-layer.pdf", hidden=False),
        "hidden_only": pdfs.hidden_only_pdf(tmp_path / "hidden-only.pdf"),
        "hidden_beside_visible": pdfs.hidden_beside_visible_pdf(tmp_path / "hidden-beside.pdf"),
        "hidden_paragraph": pdfs.hidden_paragraph_pdf(tmp_path / "hidden-paragraph.pdf"),
        "garbled": pdfs.garbled_pdf(tmp_path / "garbled.pdf"),
        "suspicious": pdfs.suspicious_pdf(tmp_path / "suspicious.pdf"),
        "rotated": pdfs.rotated_pdf(tmp_path / "rotated.pdf"),
        "labelled": pdfs.labelled_pdf(tmp_path / "labelled.pdf"),
        "unicode": pdfs.unicode_pdf(tmp_path / "unicode.pdf"),
        "margins": pdfs.repeated_margin_pdf(tmp_path / "margins.pdf"),
        "truncated": pdfs.truncated_pdf(tmp_path / "truncated.pdf", source),
    }


def test_clean_pages_with_running_margins_are_ok_and_keep_their_roles(tmp_path, config):
    report = extract_document(pdfs.policy_pdf(tmp_path / "policy.pdf"), config=config)
    assert report.page_count == 4
    assert [page.status for page in report.pages] == [PageStatus.OK] * 4
    assert all(page.quality_status is QualityStatus.VERIFIED for page in report.pages)
    first = report.pages[0]
    roles = {block.role for block in first.blocks}
    assert {BlockRole.HEADER, BlockRole.BODY, BlockRole.FOOTER} <= roles
    assert first.raw_text.startswith("ACME Policy Manual")
    assert first.raw_text.endswith("Page 1 of 4")
    assert first.printed_page is None


def test_a_unique_heading_is_not_mistaken_for_a_running_margin(tmp_path, config):
    report = extract_document(pdfs.repeated_margin_pdf(tmp_path / "margins.pdf"), config=config)
    first = report.pages[0]
    heading = next(block for block in first.blocks if "Unique opening heading" in block.lines[0].text)
    assert heading.role is BlockRole.BODY
    running = [block for block in first.blocks if block.lines and block.lines[0].text == "ACME Policy Manual"]
    assert running and all(block.role is BlockRole.HEADER for block in running)


def test_two_column_page_reads_the_left_column_first_even_when_drawn_second(tmp_path, config):
    report = extract_document(pdfs.two_column_pdf(tmp_path / "two.pdf", right_first=True), config=config)
    page = report.pages[0]
    assert page.reading_order is ReadingOrder.MULTI_COLUMN
    assert page.column_count == 2
    assert page.raw_text.index("Left column") < page.raw_text.index("Right column")
    columns = {
        block.lines[0].text[:4]: block.column_index
        for block in page.blocks
        if block.role is BlockRole.BODY
    }
    assert columns["Left"] == 0
    assert columns["Righ"] == 1


def test_full_width_heading_separates_two_column_sections(tmp_path, config):
    report = extract_document(pdfs.banded_columns_pdf(tmp_path / "banded.pdf", right_first=True), config=config)
    text = report.pages[0].raw_text
    markers = ["Top left", "Top right", "2. Scope", "Bottom left", "Bottom right"]
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_running_header_and_footer_are_kept_out_of_the_column_clustering(tmp_path, config):
    report = extract_document(pdfs.margin_columns_pdf(tmp_path / "margin-columns.pdf"), config=config)
    for page in report.pages:
        header = [block for block in page.blocks if block.role is BlockRole.HEADER]
        footer = [block for block in page.blocks if block.role is BlockRole.FOOTER]
        assert header and footer, page.pdf_page
        assert all(block.column_index is None for block in header + footer)
        body = [block for block in page.blocks if block.role is BlockRole.BODY]
        assert body and all(block.column_index in (0, 1) for block in body)
        assert page.column_count == 2
        assert page.raw_text.startswith("ACME")
        assert page.raw_text.endswith(f"Page {page.pdf_page} of 4")


def test_ragged_single_column_stays_one_column(tmp_path, config):
    report = extract_document(pdfs.ragged_column_pdf(tmp_path / "ragged.pdf"), config=config)
    page = report.pages[0]
    assert page.reading_order is ReadingOrder.SINGLE_COLUMN
    assert page.column_count == 1
    assert page.raw_text.index("First paragraph") < page.raw_text.index("Second paragraph")
    assert page.raw_text.index("Second paragraph") < page.raw_text.index("Third paragraph")


def test_ruled_table_cells_sit_on_their_own_lines_and_the_page_is_flagged(tmp_path, config):
    report = extract_document(pdfs.ruled_table_pdf(tmp_path / "table.pdf"), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.WARNING
    assert page.quality_status is QualityStatus.WARNING
    assert page.table_count == 1
    assert "table_detected" in _codes(page)
    lines = page.raw_text.split("\n")
    assert "3.5" in lines
    assert "2.0" in lines
    assert "A" in lines
    assert "contract" in lines


def test_every_block_and_line_offset_resolves_into_raw_text(tmp_path, config):
    for name, path in _all_fixtures(tmp_path).items():
        report = extract_document(path, config=config)
        for page in report.pages:
            spans = []
            for block in page.blocks:
                if block.raw_start is None:
                    assert block.role is BlockRole.IMAGE, name
                    continue
                assert page.raw_text[block.raw_start : block.raw_end] == "\n".join(
                    line.text for line in block.lines
                ), (name, page.pdf_page)
                for line in block.lines:
                    assert page.raw_text[line.raw_start : line.raw_end] == line.text, (name, page.pdf_page)
                spans.append((block.raw_start, block.raw_end))
            for (_, end), (start, _) in zip(sorted(spans), sorted(spans)[1:]):
                assert end <= start, (name, page.pdf_page)


def test_printed_labels_are_kept_apart_from_physical_page_numbers(tmp_path, config):
    report = extract_document(pdfs.labelled_pdf(tmp_path / "labelled.pdf"), config=config)
    assert [page.pdf_page for page in report.pages] == [1, 2, 3]
    assert [page.printed_page for page in report.pages] == ["i", "ii", "1"]


def test_non_ascii_text_round_trips_into_raw_text(tmp_path, config):
    report = extract_document(pdfs.unicode_pdf(tmp_path / "unicode.pdf"), config=config)
    raw = report.pages[0].raw_text
    assert pdfs.UNICODE_LINE in raw
    assert pdfs.UNICODE_CJK in raw
    assert "�" not in raw


def test_image_page_with_an_invisible_text_layer_is_unverified_and_not_ocred(tmp_path, config):
    report = extract_document(pdfs.scanned_with_text_pdf(tmp_path / "hidden.pdf", hidden=True), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.SCANNED_TEXT_LAYER
    assert page.quality_status is QualityStatus.UNVERIFIED
    assert page.extraction_method is ExtractionMethod.NATIVE_TEXT
    assert {"image_with_text_layer", "hidden_text_layer"} <= _codes(page)
    assert page.hidden_chars and page.hidden_chars > 0
    assert "Hidden OCR words here" in page.raw_text


def test_image_page_with_a_visible_text_layer_is_also_unverified(tmp_path, config):
    report = extract_document(pdfs.scanned_with_text_pdf(tmp_path / "visible.pdf", hidden=False), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.SCANNED_TEXT_LAYER
    assert page.quality_status is QualityStatus.UNVERIFIED
    assert "hidden_text_layer" not in _codes(page)


def test_invisible_text_beside_visible_text_is_a_warning(tmp_path, config):
    report = extract_document(pdfs.hidden_beside_visible_pdf(tmp_path / "beside.pdf"), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.WARNING
    assert "hidden_text_present" in _codes(page)
    assert page.visible_chars and page.hidden_chars


def test_text_that_is_only_invisible_is_suspicious(tmp_path, config):
    report = extract_document(pdfs.hidden_only_pdf(tmp_path / "hidden-only.pdf"), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.SUSPICIOUS
    assert "hidden_text_only" in _codes(page)


def test_invisible_paragraph_beside_a_short_visible_line_is_suspicious(tmp_path, config):
    report = extract_document(pdfs.hidden_paragraph_pdf(tmp_path / "hidden-paragraph.pdf"), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.SUSPICIOUS
    assert page.quality_status is QualityStatus.UNVERIFIED
    assert "hidden_text_share_high" in _codes(page)
    assert page.hidden_chars > page.visible_chars
    assert "An invisible paragraph" in page.raw_text


def test_each_line_carries_the_count_of_its_own_invisible_characters(tmp_path, config):
    report = extract_document(pdfs.hidden_beside_visible_pdf(tmp_path / "beside.pdf"), config=config)
    lines = [line for block in report.pages[0].blocks for line in block.lines]
    hidden_lines = [line for line in lines if line.hidden_chars]
    assert [line.text for line in hidden_lines] == ["hidden"]
    assert hidden_lines[0].hidden_chars == 6
    assert all(line.hidden_chars == 0 for line in lines if line.text != "hidden")


@pytest.mark.parametrize("name", ["hidden_layer", "hidden_only", "hidden_beside_visible", "hidden_paragraph"])
def test_no_page_with_invisible_text_is_ever_verified(tmp_path, config, name):
    report = extract_document(_all_fixtures(tmp_path)[name], config=config)
    for page in report.pages:
        assert page.hidden_chars, name
        assert page.status is not PageStatus.OK, name
        assert page.quality_status is not QualityStatus.VERIFIED, name


def test_image_only_page_without_tesseract_stays_scanned_with_a_reason(tmp_path, config, monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    report = extract_document(pdfs.image_only_pdf(tmp_path / "scan.pdf"), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.SCANNED
    assert page.quality_status is QualityStatus.UNVERIFIED
    assert page.extraction_method is ExtractionMethod.NONE
    assert page.raw_text == ""
    assert page.image_coverage > 0.5
    assert {"image_only_page", "ocr_unavailable"} <= _codes(page)
    assert [block.role for block in page.blocks] == [BlockRole.IMAGE]


def test_blank_page_is_blank_and_has_no_blocks(tmp_path, config):
    report = extract_document(pdfs.blank_pdf(tmp_path / "blank.pdf"), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.BLANK
    assert "blank_page" in _codes(page)
    assert page.ink_ratio is not None and page.ink_ratio <= config.blank_ink_ratio_max
    assert page.blocks == []


def test_replacement_characters_make_a_page_garbled(tmp_path, config):
    report = extract_document(pdfs.garbled_pdf(tmp_path / "garbled.pdf"), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.GARBLED
    assert page.quality_status is QualityStatus.UNVERIFIED
    assert "garbled_text" in _codes(page)


def test_letters_separated_by_spaces_make_a_page_suspicious(tmp_path, config):
    report = extract_document(pdfs.suspicious_pdf(tmp_path / "spaced.pdf"), config=config)
    page = report.pages[0]
    assert page.status is PageStatus.SUSPICIOUS
    assert "suspicious_text" in _codes(page)


def test_rotated_page_is_a_warning(tmp_path, config):
    report = extract_document(pdfs.rotated_pdf(tmp_path / "rotated.pdf"), config=config)
    page = report.pages[0]
    assert page.rotation == 90
    assert page.status is PageStatus.WARNING
    assert "page_rotated" in _codes(page)


def test_a_repaired_truncated_file_marks_every_page_as_not_verified(tmp_path, config):
    truncated = _all_fixtures(tmp_path)["truncated"]
    report = extract_document(truncated, config=config)
    codes = {issue.code for issue in report.issues}
    assert {"pdf_repaired", "pdf_missing_eof"} <= codes
    assert report.pages
    for page in report.pages:
        assert page.quality_status is not QualityStatus.VERIFIED
        assert {"pdf_repaired", "pdf_missing_eof"} <= _codes(page)
        assert all(
            issue.detail.startswith("document level: ")
            for issue in page.issues
            if issue.code in {"pdf_repaired", "pdf_missing_eof"}
        )


def test_status_counts_and_issue_codes_agree_with_the_pages(tmp_path, config):
    for name, path in _all_fixtures(tmp_path).items():
        report = extract_document(path, config=config)
        assert report.status_counts == dict(sorted(Counter(p.status.value for p in report.pages).items())), name
        for page in report.pages:
            for issue in page.issues:
                assert issue.code in ISSUE_CODES, (name, issue.code)
                assert issue.detail, (name, issue.code)
            if page.status is not PageStatus.OK:
                assert page.issues, (name, page.pdf_page)


def test_the_same_bytes_and_configuration_give_the_same_report(tmp_path, config):
    path = pdfs.two_column_pdf(tmp_path / "two.pdf", right_first=True)
    first = extract_document(path, config=config).model_dump_json()
    second = extract_document(path, config=config).model_dump_json()
    assert first == second


def test_encrypted_files_are_rejected_before_any_page_is_read(tmp_path, config):
    source = pdfs.policy_pdf(tmp_path / "source.pdf")
    encrypted = pdfs.encrypted_pdf(tmp_path / "encrypted.pdf", source)
    with pytest.raises(PdfRejectedError) as caught:
        extract_document(encrypted, config=config)
    assert caught.value.code == "encrypted_requires_password"


def test_no_files_are_written_without_an_out_root(tmp_path, config, monkeypatch):
    monkeypatch.chdir(tmp_path)
    extract_document(pdfs.ruled_table_pdf(tmp_path / "table.pdf"), config=config)
    assert not (tmp_path / "data").exists()
