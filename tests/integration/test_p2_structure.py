"""P2 exit criteria (structure, end to end): synthetic PDFs through P1 and then build_structure.

Every PDF is generated at test time and labelled synthetic, so the expected structure is known.
Run: pytest tests/integration/test_p2_structure.py -q
"""

from __future__ import annotations

import shutil

import pytest

from app.document_structure import StructureError, build_structure
from app.document_structure.models import ContentType
from app.ingestion.extract import extract_document
from tests.fixtures import structure_pdfs as fixtures
from tests.fixtures import synthetic_pdfs as pdfs
from tests.fixtures.structure_checks import check_invariants


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("p2-structure")
    path = fixtures.structure_pdf(workdir / "structure.pdf")
    extracted = extract_document(path, out_root=workdir / "p1")
    return extracted, build_structure(extracted, path), path


def _units(structure, content_type):
    return [unit for unit in structure.units if unit.content_type == content_type]


def _by_text(structure, text):
    matches = [unit for unit in structure.units if unit.raw_text == text]
    assert len(matches) == 1, f"expected one unit with text {text!r}, found {len(matches)}"
    return matches[0]


def test_sections_follow_the_font_ranks_and_the_nesting(built):
    _, structure, _ = built
    summary = [(section.title, section.level) for section in structure.sections]
    assert summary == [
        ("Risk Assessment Guide Overview", 1),
        ("1 Purpose", 2),
        ("2 Scope", 2),
        ("3 Method", 1),
    ]
    purpose, scope = structure.sections[1], structure.sections[2]
    assert purpose.parent_section_id == structure.sections[0].section_id
    assert scope.parent_section_id == structure.sections[0].section_id
    assert structure.sections[3].parent_section_id is None


def test_every_section_points_to_its_heading_unit(built):
    _, structure, _ = built
    headings = {unit.evidence_id: unit for unit in _units(structure, ContentType.HEADING)}
    for section in structure.sections:
        heading = headings[section.heading_id]
        assert heading.section_id == section.section_id
        assert heading.raw_text.startswith(section.title.split()[0])


def test_heading_text_carries_the_chain_of_titles(built):
    _, structure, _ = built
    purpose_paragraph = _by_text(structure, "The purpose of the method is to find and rank risks before they cause harm.")
    assert purpose_paragraph.heading_text == "Risk Assessment Guide Overview > 1 Purpose"


def test_wrapped_paragraph_is_one_unit_and_its_index_text_has_no_line_breaks(built):
    _, structure, _ = built
    paragraph = next(unit for unit in _units(structure, ContentType.PARAGRAPH) if unit.raw_text.startswith("This guide"))
    assert "\n" in paragraph.raw_text
    assert "\n" not in paragraph.index_text
    assert paragraph.raw_text.endswith("run those systems.")


def test_list_items_attach_to_the_intro_line(built):
    _, structure, _ = built
    intro = _by_text(structure, fixtures.INTRO_TEXT)
    items = _units(structure, ContentType.LIST_ITEM)
    assert [item.raw_text for item in items] == fixtures.BULLETS
    assert all(item.parent_id == intro.evidence_id for item in items)


def test_caption_is_attached_to_each_table_cell_and_row(built):
    _, structure, _ = built
    cells = _units(structure, ContentType.TABLE_CELL)
    assert all(cell.caption == fixtures.TABLE_CAPTION for cell in cells)
    rating_for_low = next(cell for cell in cells if cell.row_index == 1 and cell.col_index == 1)
    assert rating_for_low.raw_text == "1"
    assert rating_for_low.row_header == "Low"
    assert rating_for_low.col_header == "Rating"
    for token in ("Low", "Rating", "1", "Table 1"):
        assert token in rating_for_low.index_text


def test_row_units_state_the_header_value_pairs_and_are_derived(built):
    _, structure, _ = built
    rows = _units(structure, ContentType.TABLE_ROW)
    assert [row.row_header for row in rows] == ["Low", "High"]
    for row in rows:
        assert row.derived is True
        assert "Rating = " in row.index_text
        assert "Meaning = " in row.index_text
    low = rows[0]
    assert low.raw_text == "Low\n1\nRare"


def test_header_row_cells_carry_no_row_header_and_are_units(built):
    _, structure, _ = built
    header = [cell for cell in _units(structure, ContentType.TABLE_CELL) if cell.row_index == 0]
    assert [cell.raw_text for cell in header] == ["Level", "Rating", "Meaning"]
    assert all(cell.row_header is None and cell.col_header is None for cell in header)


def test_table_cells_mirror_the_cell_units(built):
    _, structure, _ = built
    cells = _units(structure, ContentType.TABLE_CELL)
    assert len(structure.table_cells) == len(cells) == 9
    assert {record.evidence_id for record in structure.table_cells} == {cell.evidence_id for cell in cells}


def test_footnote_is_a_footnote_unit(built):
    _, structure, _ = built
    footnote = _units(structure, ContentType.FOOTNOTE)
    assert [unit.raw_text for unit in footnote] == [fixtures.FOOTNOTE_TEXT]


def test_running_headers_and_page_numbers_are_kept_but_not_body_retrieval(built):
    _, structure, _ = built
    furniture = _units(structure, ContentType.HEADER) + _units(structure, ContentType.FOOTER)
    assert furniture, "the running header and the page numbers must be kept as units"
    assert all(unit.body_retrieval is False for unit in furniture)
    body = [unit for unit in structure.units if unit.body_retrieval]
    assert not any(fixtures.RUNNING_HEADER == unit.raw_text for unit in body)


def test_units_keep_the_page_numbers_and_quality_of_their_page(built):
    extracted, structure, _ = built
    qualities = {page.pdf_page: page.quality_status.value for page in extracted.pages}
    for unit in structure.units:
        assert unit.pdf_page in qualities
        assert unit.extraction_quality.value != "verified" or qualities[unit.pdf_page] == "verified"
    assert {unit.printed_page for unit in structure.units} == {None}


def test_invariants_hold_for_the_structure_fixture(built):
    extracted, structure, _ = built
    check_invariants(extracted, structure)


def test_structure_is_deterministic(built, tmp_path):
    extracted, structure, path = built
    copy = tmp_path / "copy.pdf"
    shutil.copyfile(path, copy)
    again = build_structure(extracted, copy)
    assert again.model_dump_json() == structure.model_dump_json()


def test_pdf_that_does_not_match_the_report_is_refused(built, tmp_path):
    extracted, _, path = built
    changed = tmp_path / "changed.pdf"
    shutil.copyfile(path, changed)
    with changed.open("ab") as handle:
        handle.write(b"\n% a change after extraction\n")
    with pytest.raises(StructureError, match="SHA-256"):
        build_structure(extracted, changed)


def test_missing_pdf_is_reported(built, tmp_path):
    extracted, _, _ = built
    with pytest.raises(StructureError, match="not found"):
        build_structure(extracted, tmp_path / "absent.pdf")


def test_a_single_heading_size_is_not_a_level(tmp_path):
    path = fixtures.two_heading_sizes_pdf(tmp_path / "single.pdf")
    extracted = extract_document(path, out_root=tmp_path / "p1")
    structure = build_structure(extracted, path)
    assert [section.title for section in structure.sections] == ["Single Title Line"]
    assert structure.sections[0].level == 1
    check_invariants(extracted, structure)


def test_image_only_page_has_no_units_and_is_recorded(tmp_path):
    path = pdfs.image_only_pdf(tmp_path / "scan.pdf")
    extracted = extract_document(path, out_root=tmp_path / "p1")
    structure = build_structure(extracted, path)
    assert structure.units == []
    assert [issue.code for issue in structure.issues] == ["page_unstructured"]
    check_invariants(extracted, structure)


def test_unverified_text_layer_gets_block_units_only(tmp_path):
    path = pdfs.scanned_with_text_pdf(tmp_path / "ocr-layer.pdf", hidden=False)
    extracted = extract_document(path, out_root=tmp_path / "p1")
    structure = build_structure(extracted, path)
    assert structure.sections == []
    assert structure.table_cells == []
    body = [unit for unit in structure.units if unit.body_retrieval]
    assert body, "the text layer must still be kept as units"
    assert all(unit.content_type == ContentType.PAGE_TEXT for unit in body)
    assert all(unit.extraction_quality.value == "unverified" for unit in body)
    check_invariants(extracted, structure)


def test_text_made_invisible_by_render_mode_is_never_verified(tmp_path):
    path = pdfs.hidden_beside_visible_pdf(tmp_path / "hidden.pdf")
    extracted = extract_document(path, out_root=tmp_path / "p1")
    structure = build_structure(extracted, path)
    hidden_lines = [
        line.text
        for page in extracted.pages
        for block in page.blocks
        for line in block.lines
        if line.hidden_chars > 0
    ]
    assert hidden_lines, "the fixture must contain invisible text"
    for unit in structure.units:
        if any(line in unit.raw_text for line in hidden_lines):
            assert unit.extraction_quality.value == "unverified", unit.evidence_id
    check_invariants(extracted, structure)
