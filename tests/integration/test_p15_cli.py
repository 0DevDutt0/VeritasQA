"""P15: the document comparison through the command line, on synthetic PDFs (ARCHITECTURE §20).

Every PDF is written in tmp_path, and the store, the extraction outputs and the reports are in tmp_path too, so the
owner's data folders are never read or written.
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from app.api.cli import main
from tests.fixtures.synthetic_pdfs import _image_png

WEEKS = "The limit is 30 days after approval."
CHANGED_WEEKS = "The limit is 31 days after approval."
FILLER = "Applications are reviewed by the front desk every working day."


def _pdf(path: Path, pages: list[str | None]) -> Path:
    """One page per entry: text, ``""`` for a blank page, or ``None`` for a scanned page (an image, no text)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    for text in pages:
        page = document.new_page()
        if text is None:
            page.insert_image(page.rect, stream=_image_png())
        elif text:
            page.insert_textbox(fitz.Rect(72, 110, 523, 300), text, fontsize=11)
    document.save(str(path))
    document.close()
    return path


def _version(workspace: dict, version: str, pages: list[str | None]) -> Path:
    """A PDF named ``policy.pdf`` in its own folder, so two versions share a file name and differ in content."""
    return _pdf(workspace["dir"] / version / "policy.pdf", pages)


@pytest.fixture
def workspace(tmp_path):
    return {
        "dir": tmp_path,
        "store": tmp_path / "store.sqlite",
        "extracted": tmp_path / "extracted",
        "reports": tmp_path / "reports",
    }


def _run(capsys, argv: list[str]) -> tuple[int, dict | None, dict | None]:
    code = main(argv)
    captured = capsys.readouterr()
    out = json.loads(captured.out) if captured.out.strip() else None
    err = json.loads(captured.err) if captured.err.strip() else None
    return code, out, err


def _ingest(capsys, workspace: dict, pdf: Path, *extra: str) -> dict:
    code, out, err = _run(
        capsys,
        [
            "ingest",
            str(pdf),
            "--store",
            str(workspace["store"]),
            "--extracted-root",
            str(workspace["extracted"]),
            "--report-dir",
            str(workspace["reports"]),
            *extra,
        ],
    )
    assert code == 0, err
    return out


def _stored_ids(capsys, workspace: dict) -> list[str]:
    code, out, _ = _run(capsys, ["report", "--store", str(workspace["store"])])
    assert code == 0
    return [document["document_id"] for document in out["documents"]]


def test_the_first_upload_has_no_earlier_version_and_says_so(workspace, capsys):
    out = _ingest(capsys, workspace, _version(workspace, "v1", [WEEKS]))
    assert out["qa"]["status"] == "not_run"
    assert "no earlier version named 'policy.pdf'" in out["qa"]["reason"]
    assert out["qa"]["report_path"] is None


def test_a_second_upload_of_the_same_file_name_is_compared_page_by_page_and_reported(workspace, capsys):
    first = _ingest(capsys, workspace, _version(workspace, "v1", [WEEKS, FILLER]))
    second = _ingest(capsys, workspace, _version(workspace, "v2", [CHANGED_WEEKS, FILLER]))
    qa = second["qa"]
    assert qa["status"] == "compared"
    assert qa["earlier_document_id"] == first["document_id"]
    assert qa["text_identical"] is False
    assert qa["counts"]["changed"] == 1 and qa["counts"]["unchanged"] == 1
    (difference,) = qa["differences"]
    assert (difference["kind"], difference["old_page"], difference["new_page"]) == ("changed", 1, 1)
    (change,) = difference["changes"]
    assert (change["removed"], change["added"]) == ("30", "31")
    report = Path(qa["report_path"])
    assert report.name == f"{second['document_id']}-vs-{first['document_id']}.txt"
    assert "earlier page 1 -> new page 1: changed" in report.read_text(encoding="utf-8")


def test_uploading_the_same_file_again_is_identical_and_compares_nothing(workspace, capsys):
    pdf = _version(workspace, "v1", [WEEKS])
    _ingest(capsys, workspace, pdf)
    again = _ingest(capsys, workspace, pdf)
    assert again["qa"]["status"] == "identical"
    assert again["qa"]["report_path"] is None
    assert len(_stored_ids(capsys, workspace)) == 1


def test_two_earlier_versions_stop_the_comparison_until_one_is_named(workspace, capsys):
    first = _ingest(capsys, workspace, _version(workspace, "v1", [WEEKS]))
    second = _ingest(capsys, workspace, _version(workspace, "v2", [CHANGED_WEEKS]))
    third_pdf = _version(workspace, "v3", [WEEKS, FILLER])
    third = _ingest(capsys, workspace, third_pdf)
    assert third["qa"]["status"] == "not_run"
    assert third["qa"]["candidates"] == [first["document_id"], second["document_id"]]
    assert "--against <document_id>" in third["qa"]["reason"]
    named = _ingest(capsys, workspace, third_pdf, "--against", first["document_id"])
    assert named["qa"]["status"] == "compared"
    assert named["qa"]["earlier_document_id"] == first["document_id"]


def test_an_unknown_against_document_is_an_error_and_stores_nothing(workspace, capsys):
    first = _ingest(capsys, workspace, _version(workspace, "v1", [WEEKS]))
    code, out, err = _run(
        capsys,
        [
            "ingest",
            str(_version(workspace, "v2", [CHANGED_WEEKS])),
            "--store",
            str(workspace["store"]),
            "--extracted-root",
            str(workspace["extracted"]),
            "--report-dir",
            str(workspace["reports"]),
            "--against",
            "doc-0000000000000000",
        ],
    )
    assert code == 1 and out is None
    assert "doc-0000000000000000" in err["error"]["message"]
    assert _stored_ids(capsys, workspace) == [first["document_id"]]


def test_compare_compares_two_stored_documents_without_ingesting_again(workspace, capsys):
    first = _ingest(capsys, workspace, _version(workspace, "v1", [WEEKS]))
    second = _ingest(capsys, workspace, _version(workspace, "v2", [CHANGED_WEEKS]))
    code, out, err = _run(
        capsys,
        ["compare", "--store", str(workspace["store"]), "--document-id", first["document_id"], "--against", second["document_id"], "--report-dir", str(workspace["reports"])],
    )
    assert code == 0, err
    assert out["document_id"] == first["document_id"]
    assert out["qa"]["status"] == "compared"
    (difference,) = out["qa"]["differences"]
    # The earlier version is now the second document, so the removed and added words swap.
    assert (difference["changes"][0]["removed"], difference["changes"][0]["added"]) == ("31", "30")
    assert len(_stored_ids(capsys, workspace)) == 2


def test_compare_refuses_one_document_against_itself_and_an_unknown_document(workspace, capsys):
    first = _ingest(capsys, workspace, _version(workspace, "v1", [WEEKS]))
    code, _, err = _run(
        capsys,
        ["compare", "--store", str(workspace["store"]), "--document-id", first["document_id"], "--against", first["document_id"]],
    )
    assert code == 1 and "two different documents" in err["error"]["message"]
    code, _, err = _run(capsys, ["compare", "--store", str(workspace["store"]), "--document-id", "doc-0000000000000000"])
    assert code == 1 and "not in the store" in err["error"]["message"]


def test_a_scanned_page_with_no_text_is_not_comparable(workspace, capsys):
    _ingest(capsys, workspace, _version(workspace, "v1", [WEEKS, None]))
    second = _ingest(capsys, workspace, _version(workspace, "v2", [WEEKS, FILLER]))
    qa = second["qa"]
    assert qa["counts"]["not_comparable"] == 1
    assert qa["text_identical"] is False
    (difference,) = qa["differences"]
    assert (difference["kind"], difference["old_page"], difference["new_page"]) == ("not_comparable", 2, 2)
    assert difference["reason"] == "no readable text on the earlier page"


def test_a_changed_page_with_a_warning_is_compared_and_the_warning_is_shown(workspace, capsys):
    _ingest(capsys, workspace, _scanned_with_text(workspace, "v1", "Visible words here about the limit."))
    second = _ingest(capsys, workspace, _scanned_with_text(workspace, "v2", "Visible words here about the rule."))
    (difference,) = second["qa"]["differences"]
    assert difference["kind"] == "changed"
    assert difference["old_warnings"], "the earlier page's warning is shown"
    report = Path(second["qa"]["report_path"]).read_text(encoding="utf-8")
    assert "warnings, earlier page:" in report


def test_a_report_that_cannot_be_written_is_recorded_and_the_document_is_still_stored(workspace, capsys):
    workspace["reports"].write_text("not a folder", encoding="utf-8")
    _ingest(capsys, workspace, _version(workspace, "v1", [WEEKS]))
    code, out, err = _run(
        capsys,
        [
            "ingest",
            str(_version(workspace, "v2", [CHANGED_WEEKS])),
            "--store",
            str(workspace["store"]),
            "--extracted-root",
            str(workspace["extracted"]),
            "--report-dir",
            str(workspace["reports"]),
        ],
    )
    assert code == 0, err
    assert out["qa"]["status"] == "compared"
    assert out["qa"]["report_path"] is None
    assert out["qa"]["report_error"]
    assert len(_stored_ids(capsys, workspace)) == 2


def _scanned_with_text(workspace: dict, version: str, text: str) -> Path:
    """A full-page image with a visible text layer, so the page has text and a status that carries a warning."""
    path = workspace["dir"] / version / "policy.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_image(page.rect, stream=_image_png())
    page.insert_text((72, 100), text, fontsize=12)
    document.save(str(path))
    document.close()
    return path
