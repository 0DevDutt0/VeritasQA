"""P1 exit criteria (rendering and OCR adapter): PNG output, ink measure and a stubbed tesseract.

The stub (tests/fixtures/fake_tesseract.py) checks the argument list it receives, so these tests
cover the adapter without a real binary. The real-binary test runs only when tesseract is on PATH.
Run:  pytest tests/unit/test_p1_render_ocr.py -q
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from app.ingestion import ocr
from app.ingestion.errors import OcrError, RenderError
from app.ingestion.render import ink_ratio, render_page_png
from tests.fixtures import synthetic_pdfs as pdfs

STUB = Path(__file__).resolve().parents[1] / "fixtures" / "fake_tesseract.py"
STUB_COMMAND = [sys.executable, str(STUB)]


def test_render_page_png_writes_a_png_at_the_requested_size(tmp_path):
    source = pdfs.policy_pdf(tmp_path / "policy.pdf")
    target = render_page_png(source, 1, 72, tmp_path / "renders" / "p0001.png")
    assert target.is_file()
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    pixmap = fitz.Pixmap(str(target))
    assert (pixmap.width, pixmap.height) == (595, 842)


def test_render_page_png_rejects_a_page_outside_the_document(tmp_path):
    source = pdfs.policy_pdf(tmp_path / "policy.pdf")
    with pytest.raises(RenderError, match="outside"):
        render_page_png(source, 9, 72, tmp_path / "p.png")


def test_render_page_png_rejects_a_non_positive_dpi(tmp_path):
    source = pdfs.policy_pdf(tmp_path / "policy.pdf")
    with pytest.raises(RenderError, match="positive"):
        render_page_png(source, 1, 0, tmp_path / "p.png")


def test_ink_ratio_is_zero_for_a_blank_page_and_high_for_an_image(tmp_path):
    blank = pdfs.blank_pdf(tmp_path / "blank.pdf")
    scan = pdfs.image_only_pdf(tmp_path / "scan.pdf")
    with fitz.open(blank) as document:
        blank_pixmap = document[0].get_pixmap(dpi=36, colorspace=fitz.csGRAY, alpha=False)
        assert ink_ratio(blank_pixmap) == 0.0
    with fitz.open(scan) as document:
        scan_pixmap = document[0].get_pixmap(dpi=36, colorspace=fitz.csGRAY, alpha=False)
        assert ink_ratio(scan_pixmap) > 0.5


def test_ink_ratio_refuses_a_colour_pixmap(tmp_path):
    source = pdfs.policy_pdf(tmp_path / "policy.pdf")
    with fitz.open(source) as document:
        colour = document[0].get_pixmap(dpi=36, alpha=False)
    with pytest.raises(RenderError, match="greyscale"):
        ink_ratio(colour)


def test_tesseract_availability_follows_the_path(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    assert ocr.tesseract_available() is False
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "C:/tools/tesseract.exe")
    assert ocr.tesseract_available() is True


def test_stub_receives_the_exact_argument_list_and_its_text_is_returned(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"not really a png; the stub only checks that the file exists")
    text = ocr.ocr_page(image, language="eng", timeout_seconds=30, command=STUB_COMMAND)
    assert text == "Stub OCR language eng\nStub OCR line two"


def test_stub_failure_becomes_an_ocr_error(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    image.write_bytes(b"x")
    monkeypatch.setenv("FAKE_TESSERACT_MODE", "fail")
    with pytest.raises(OcrError, match="status 3"):
        ocr.ocr_page(image, language="eng", timeout_seconds=30, command=STUB_COMMAND)


def test_adapter_runs_the_command_without_a_shell(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    image.write_bytes(b"x")
    seen: dict = {}
    original_run = subprocess.run

    def spy(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return original_run(argv, **kwargs)

    monkeypatch.setattr(ocr.subprocess, "run", spy)
    ocr.ocr_page(image, language="eng", timeout_seconds=30, command=STUB_COMMAND)
    assert isinstance(seen["argv"], list)
    assert seen["kwargs"].get("shell", False) is False


def test_without_a_binary_or_command_the_adapter_refuses_to_run(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    with pytest.raises(OcrError, match="not on PATH"):
        ocr.ocr_page(image, language="eng", timeout_seconds=30)


def test_an_empty_command_is_rejected(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"x")
    with pytest.raises(OcrError, match="empty"):
        ocr.ocr_page(image, language="eng", timeout_seconds=30, command=[])


@pytest.mark.requires_tesseract
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is not on PATH")
def test_real_tesseract_reads_a_rendered_line(tmp_path):
    source = pdfs.policy_pdf(tmp_path / "policy.pdf")
    image = render_page_png(source, 1, 300, tmp_path / "page.png")
    text = ocr.ocr_page(image, language="eng", timeout_seconds=120)
    assert "contract" in text.lower()
