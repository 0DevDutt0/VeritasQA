"""P1 exit criteria (validation): files are accepted or rejected with fixed codes before any page is parsed.

Every PDF here is generated at test time (synthetic). Run:  pytest tests/unit/test_p1_validate.py -q
"""

from __future__ import annotations

import hashlib
import re

import pytest

from app.ingestion.config import load_ingestion_config
from app.ingestion.errors import REJECTION_CODES, PdfRejectedError
from app.ingestion.validate import document_id_for, validate_pdf
from tests.fixtures import synthetic_pdfs as pdfs


@pytest.fixture
def config():
    return load_ingestion_config()


def test_valid_pdf_is_accepted_with_a_hash_based_document_id(tmp_path, config):
    path = pdfs.policy_pdf(tmp_path / "policy.pdf")
    info = validate_pdf(path, config)
    assert info.source_name == "policy.pdf"
    assert info.page_count == 4
    assert info.size_bytes == path.stat().st_size
    assert info.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert re.fullmatch(r"doc-[0-9a-f]{16}", info.document_id)
    assert info.document_id == document_id_for(info.sha256)
    assert info.is_repaired is False
    assert info.has_eof_marker is True


def test_document_id_survives_a_rename_and_changes_with_the_content(tmp_path, config):
    original = pdfs.policy_pdf(tmp_path / "a.pdf")
    renamed = tmp_path / "renamed.pdf"
    renamed.write_bytes(original.read_bytes())
    changed = tmp_path / "changed.pdf"
    changed.write_bytes(original.read_bytes() + b"\n% an appended comment\n")
    original_id = validate_pdf(original, config).document_id
    assert validate_pdf(renamed, config).document_id == original_id
    assert validate_pdf(changed, config).document_id != original_id


def test_missing_file_is_rejected(tmp_path, config):
    with pytest.raises(PdfRejectedError) as caught:
        validate_pdf(tmp_path / "absent.pdf", config)
    assert caught.value.code == "file_missing"


def test_empty_file_is_rejected(tmp_path, config):
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    with pytest.raises(PdfRejectedError) as caught:
        validate_pdf(path, config)
    assert caught.value.code == "file_empty"


def test_oversized_file_is_rejected(tmp_path, config):
    path = pdfs.policy_pdf(tmp_path / "policy.pdf")
    small_limit = config.model_copy(update={"max_file_bytes": 100})
    with pytest.raises(PdfRejectedError) as caught:
        validate_pdf(path, small_limit)
    assert caught.value.code == "file_too_large"


def test_file_without_the_pdf_header_is_rejected(tmp_path, config):
    path = tmp_path / "notes.pdf"
    path.write_text("Just a text file, not a PDF.", encoding="utf-8")
    with pytest.raises(PdfRejectedError) as caught:
        validate_pdf(path, config)
    assert caught.value.code == "bad_header"


def test_pdf_header_without_pdf_structure_is_rejected_by_pymupdf(tmp_path, config):
    path = pdfs.junk_pdf(tmp_path / "junk.pdf")
    with pytest.raises(PdfRejectedError) as caught:
        validate_pdf(path, config)
    assert caught.value.code == "cannot_open"


def test_encrypted_file_that_needs_a_password_is_rejected(tmp_path, config):
    source = pdfs.policy_pdf(tmp_path / "source.pdf")
    encrypted = pdfs.encrypted_pdf(tmp_path / "encrypted.pdf", source)
    with pytest.raises(PdfRejectedError) as caught:
        validate_pdf(encrypted, config)
    assert caught.value.code == "encrypted_requires_password"


def test_truncated_file_is_accepted_and_marked_as_repaired(tmp_path, config):
    source = pdfs.policy_pdf(tmp_path / "source.pdf")
    truncated = pdfs.truncated_pdf(tmp_path / "truncated.pdf", source)
    info = validate_pdf(truncated, config)
    assert info.is_repaired is True
    assert info.has_eof_marker is False
    assert info.page_count >= 1


def test_rejection_codes_are_fixed_and_checked():
    assert "encrypted_requires_password" in REJECTION_CODES
    with pytest.raises(ValueError):
        PdfRejectedError("made_up_code", "not a documented code")
