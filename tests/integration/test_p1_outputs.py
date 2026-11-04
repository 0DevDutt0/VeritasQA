"""P1 exit criteria (outputs): the report, the page texts and the renders follow ARCHITECTURE §10.

Run:  pytest tests/integration/test_p1_outputs.py -q
"""

from __future__ import annotations

import hashlib
import re

import pytest

from app.ingestion.config import config_fingerprint, load_ingestion_config
from app.ingestion.errors import IngestionError
from app.ingestion.extract import extract_document
from app.ingestion.models import PageStatus
from app.ingestion.report import load_outputs
from tests.fixtures import synthetic_pdfs as pdfs


@pytest.fixture
def config():
    return load_ingestion_config()


def test_outputs_follow_the_documented_layout(tmp_path, config):
    pdf = pdfs.ruled_table_pdf(tmp_path / "table.pdf")
    out = tmp_path / "out"
    report = extract_document(pdf, config=config, out_root=out)
    base = out / report.document_id
    assert (base / "extraction_report.json").is_file()
    page = report.pages[0]
    assert page.raw_text_path == "pages/p0001.txt"
    assert page.render_path == "renders/p0001.png"
    assert (base / "pages" / "p0001.txt").read_bytes() == page.raw_text.encode("utf-8")
    assert (base / "renders" / "p0001.png").is_file()
    assert hashlib.sha256(page.raw_text.encode("utf-8")).hexdigest() == page.raw_text_sha256


def test_pages_with_no_flags_get_no_render(tmp_path, config):
    out = tmp_path / "out"
    report = extract_document(pdfs.policy_pdf(tmp_path / "policy.pdf"), config=config, out_root=out)
    assert all(page.status is PageStatus.OK for page in report.pages)
    assert all(page.render_path is None for page in report.pages)
    assert not (out / report.document_id / "renders").exists()


def test_reports_and_page_texts_are_byte_identical_across_runs(tmp_path, config):
    path = pdfs.banded_columns_pdf(tmp_path / "banded.pdf", right_first=True)
    first = extract_document(path, config=config, out_root=tmp_path / "run-1")
    second = extract_document(path, config=config, out_root=tmp_path / "run-2")
    report_one = (tmp_path / "run-1" / first.document_id / "extraction_report.json").read_bytes()
    report_two = (tmp_path / "run-2" / second.document_id / "extraction_report.json").read_bytes()
    assert report_one == report_two
    for page in first.pages:
        text_one = (tmp_path / "run-1" / first.document_id / "pages" / f"p{page.pdf_page:04d}.txt").read_bytes()
        text_two = (tmp_path / "run-2" / second.document_id / "pages" / f"p{page.pdf_page:04d}.txt").read_bytes()
        assert text_one == text_two


def test_report_has_no_timestamps_and_no_absolute_paths(tmp_path, config):
    out = tmp_path / "out"
    report = extract_document(pdfs.ruled_table_pdf(tmp_path / "table.pdf"), config=config, out_root=out)
    text = (out / report.document_id / "extraction_report.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in text
    assert tmp_path.as_posix() not in text
    assert not re.search(r'"(created|created_at|timestamp|time|modified)', text)
    assert report.source_name == "table.pdf"


def test_report_records_the_configuration_and_the_library_versions(tmp_path, config):
    report = extract_document(pdfs.policy_pdf(tmp_path / "policy.pdf"), config=config)
    assert report.config_sha256 == config_fingerprint(config)
    assert report.extractor_version.startswith("p1-")
    assert report.pymupdf_version.startswith("1.26")
    assert report.pdfplumber_version
    assert report.schema_version == 1


def test_a_rerun_removes_generated_files_it_no_longer_needs(tmp_path, config):
    out = tmp_path / "out"
    path = pdfs.ruled_table_pdf(tmp_path / "table.pdf")
    report = extract_document(path, config=config, out_root=out)
    stale = out / report.document_id / "renders" / "p0099.png"
    stale.write_bytes(b"left over from an earlier run")
    extract_document(path, config=config, out_root=out)
    assert not stale.exists()
    assert (out / report.document_id / "renders" / "p0001.png").is_file()


def test_a_written_report_loads_back_with_its_page_texts(tmp_path, config):
    out = tmp_path / "out"
    report = extract_document(
        pdfs.banded_columns_pdf(tmp_path / "banded.pdf", right_first=True), config=config, out_root=out
    )
    loaded = load_outputs(out / report.document_id / "extraction_report.json")
    assert loaded.model_dump() == report.model_dump()


def test_a_page_text_file_changed_after_the_report_is_refused(tmp_path, config):
    out = tmp_path / "out"
    report = extract_document(pdfs.ruled_table_pdf(tmp_path / "table.pdf"), config=config, out_root=out)
    page_file = out / report.document_id / "pages" / "p0001.txt"
    page_file.write_text(page_file.read_text(encoding="utf-8") + " tampered", encoding="utf-8")
    with pytest.raises(IngestionError, match="changed"):
        load_outputs(out / report.document_id / "extraction_report.json")
