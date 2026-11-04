"""P1 exit criteria (OCR fallback, end to end): a stubbed tesseract is used on scanned pages only.

The stub (tests/fixtures/fake_tesseract.py) stands in for the binary, and it checks the argument
list it receives. Run: pytest tests/integration/test_p1_ocr_pipeline.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.ingestion import ocr
from app.ingestion.config import load_ingestion_config
from app.ingestion.extract import extract_document
from app.ingestion.models import BlockRole, ExtractionMethod, PageStatus, QualityStatus
from tests.fixtures import synthetic_pdfs as pdfs

STUB_COMMAND = [sys.executable, str(Path(__file__).resolve().parents[1] / "fixtures" / "fake_tesseract.py")]


@pytest.fixture
def config():
    return load_ingestion_config()


def _codes(page) -> set[str]:
    return {issue.code for issue in page.issues}


def test_scanned_page_becomes_unverified_ocr_text(tmp_path, config):
    report = extract_document(
        pdfs.image_only_pdf(tmp_path / "scan.pdf"),
        config=config,
        ocr_command=STUB_COMMAND,
    )
    page = report.pages[0]
    assert page.status is PageStatus.OCR_TEXT
    assert page.quality_status is QualityStatus.UNVERIFIED
    assert page.extraction_method is ExtractionMethod.OCR_TESSERACT
    assert page.raw_text == "Stub OCR language eng\nStub OCR line two"
    assert [block.role for block in page.blocks] == [BlockRole.OCR, BlockRole.IMAGE]
    assert page.blocks[0].block_no == -1
    assert {"image_only_page", "ocr_text_unverified"} <= _codes(page)
    assert "ocr_unavailable" not in _codes(page)


def test_a_failing_tesseract_leaves_the_page_scanned_and_says_why(tmp_path, config, monkeypatch):
    monkeypatch.setenv("FAKE_TESSERACT_MODE", "fail")
    report = extract_document(pdfs.image_only_pdf(tmp_path / "scan.pdf"), config=config, ocr_command=STUB_COMMAND)
    page = report.pages[0]
    assert page.status is PageStatus.SCANNED
    assert page.raw_text == ""
    assert "ocr_failed" in _codes(page)


def test_tesseract_with_no_output_is_reported(tmp_path, config, monkeypatch):
    monkeypatch.setenv("FAKE_TESSERACT_MODE", "empty")
    report = extract_document(pdfs.image_only_pdf(tmp_path / "scan.pdf"), config=config, ocr_command=STUB_COMMAND)
    page = report.pages[0]
    assert page.status is PageStatus.SCANNED
    assert "ocr_no_text" in _codes(page)


def test_ocr_switched_off_is_reported_as_disabled_not_unavailable(tmp_path, config, monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda name: pytest.fail("tesseract must not be searched for"))
    off = config.model_copy(update={"ocr_mode": "off"})
    report = extract_document(pdfs.image_only_pdf(tmp_path / "scan.pdf"), config=off)
    page = report.pages[0]
    assert page.status is PageStatus.SCANNED
    assert "ocr_disabled" in _codes(page)
    assert "ocr_unavailable" not in _codes(page)
    disabled = next(issue for issue in page.issues if issue.code == "ocr_disabled")
    assert disabled.severity == "info"


def test_a_page_with_a_text_layer_is_never_sent_to_ocr(tmp_path, config, monkeypatch):
    monkeypatch.setenv("FAKE_TESSERACT_MODE", "fail")  # would fail loudly if OCR ran
    report = extract_document(
        pdfs.scanned_with_text_pdf(tmp_path / "hidden.pdf", hidden=True),
        config=config,
        ocr_command=STUB_COMMAND,
    )
    page = report.pages[0]
    assert page.status is PageStatus.SCANNED_TEXT_LAYER
    assert "Hidden OCR words here" in page.raw_text
    assert "ocr_failed" not in _codes(page)
