"""P10 end to end: the command line on real PDFs, with two documents in one store (ARCHITECTURE §19).

The PDFs are written in tmp_path with PyMuPDF, each with one known sentence. The store, the extraction outputs and the
run files are in tmp_path too, so the owner's data folders are never read or written.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from app.api.cli import REPO_ROOT, main
from app.ingestion.validate import document_id_for
from app.storage import Store

LOANS_SENTENCE = "The limit for loans is 30 days after approval."
# Both documents use the word "limit", so a leak between them would not be hidden by a lack of shared words.
PARKING_SENTENCE = "The limit for parking permits is 25 euros per year."
LOANS_QUESTION = "How many days is the limit for loans?"
PARKING_QUESTION = "How many euros is the limit for parking permits?"
# The base-14 fonts used by _pdf cannot draw accented letters reliably (synthetic_pdfs.unicode_pdf says so), so the
# accent comes from the question, which the response echoes. The sentence has no café, so the answer is abstention.
CAFE_QUESTION = "How many days is the limit for the café licence?"


def _pdf(path: Path, sentence: str) -> Path:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(72, 110, 523, 300), sentence, fontsize=11)
    document.save(str(path))
    document.close()
    return path


def _gold(path: Path) -> Path:
    records = [
        {
            "record_id": "cli-loans-dev",
            "question": LOANS_QUESTION,
            "category": "numeric_date",
            "source": "synthetic",
            "split": "dev",
            "annotator": "cli-test",
            "expected_status": "ANSWERED",
            "evidence": [{"component": 1, "pdf_page": 1, "quote": LOANS_SENTENCE}],
            "answers": [{"component": 1, "text": "30 days"}],
        },
        {
            "record_id": "cli-parking-heldout",
            "question": PARKING_QUESTION,
            "category": "unanswerable",
            "source": "synthetic",
            "split": "heldout",
            "annotator": "cli-test",
            "expected_status": "INSUFFICIENT_EVIDENCE",
            "evidence": [],
            "answers": [],
        },
    ]
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def workspace(tmp_path):
    return {
        "store": tmp_path / "store.sqlite",
        "extracted": tmp_path / "extracted",
        "runs": tmp_path / "runs",
        "loans_pdf": _pdf(tmp_path / "loans.pdf", LOANS_SENTENCE),
        "parking_pdf": _pdf(tmp_path / "parking.pdf", PARKING_SENTENCE),
        "gold": _gold(tmp_path / "gold.jsonl"),
    }


def _invoke(capsys, argv: list[str]) -> tuple[int, dict | None, dict | None]:
    code = main(argv)
    captured = capsys.readouterr()
    out = json.loads(captured.out) if captured.out.strip() else None
    err = json.loads(captured.err) if captured.err.strip() else None
    return code, out, err


def _ingest(capsys, workspace: dict, pdf: Path) -> str:
    code, out, err = _invoke(
        capsys,
        ["ingest", str(pdf), "--store", str(workspace["store"]), "--extracted-root", str(workspace["extracted"])],
    )
    assert code == 0, err
    return out["document_id"]


def _ask(workspace: dict, document_id: str, question: str) -> list[str]:
    return ["ask", "--store", str(workspace["store"]), "--document-id", document_id, question]


def test_ingest_gives_the_document_id_of_the_file_and_ask_answers_with_its_quotation(workspace, capsys):
    document_id = _ingest(capsys, workspace, workspace["loans_pdf"])
    digest = hashlib.sha256(workspace["loans_pdf"].read_bytes()).hexdigest()
    assert document_id == document_id_for(digest)

    code, out, err = _invoke(capsys, _ask(workspace, document_id, LOANS_QUESTION))
    assert code == 0 and err is None
    assert out["status"] == "ANSWERED"
    assert [span["text"] for span in out["answer_spans"]] == ["30 days"]
    assert out["evidence"][0]["quote"] == LOANS_SENTENCE
    assert out["evidence"][0]["pdf_page"] == 1


def test_ingesting_the_same_file_again_replaces_its_rows_and_adds_no_copy(workspace, capsys):
    first = _ingest(capsys, workspace, workspace["loans_pdf"])
    second = _ingest(capsys, workspace, workspace["loans_pdf"])
    assert first == second
    code, out, _ = _invoke(capsys, ["report", "--store", str(workspace["store"])])
    assert code == 0
    assert [item["document_id"] for item in out["documents"]] == [first]


def test_two_documents_share_a_store_and_no_answer_crosses_between_them(workspace, capsys):
    loans = _ingest(capsys, workspace, workspace["loans_pdf"])
    parking = _ingest(capsys, workspace, workspace["parking_pdf"])
    assert loans != parking

    # Positive controls: each question is answered from its own document.
    code, out, _ = _invoke(capsys, _ask(workspace, loans, LOANS_QUESTION))
    assert code == 0 and out["status"] == "ANSWERED"
    code, out, _ = _invoke(capsys, _ask(workspace, parking, PARKING_QUESTION))
    assert code == 0 and out["status"] == "ANSWERED"

    # The other document's question, asked of this document: no answer, and only this document's evidence.
    for document_id, question, foreign_word in ((loans, PARKING_QUESTION, "parking"), (parking, LOANS_QUESTION, "loans")):
        code, out, err = _invoke(capsys, _ask(workspace, document_id, question))
        assert code == 0 and err is None
        assert out["status"] != "ANSWERED"
        assert out["answer_spans"] == []
        assert all(item["evidence_id"].startswith(document_id + ":") for item in out["evidence"])
        assert all(foreign_word not in item["quote"].lower() for item in out["evidence"])


def test_an_unknown_document_is_an_error_and_not_an_abstention(workspace, capsys):
    _ingest(capsys, workspace, workspace["loans_pdf"])
    code, out, err = _invoke(capsys, _ask(workspace, "doc-" + "0" * 16, LOANS_QUESTION))
    assert code == 1
    assert out is None
    assert err["error"]["type"] == "CliError"
    assert "is not in the store" in err["error"]["message"]


def test_report_lists_every_document_and_describes_the_pages_of_one(workspace, capsys):
    loans = _ingest(capsys, workspace, workspace["loans_pdf"])
    parking = _ingest(capsys, workspace, workspace["parking_pdf"])

    code, out, _ = _invoke(capsys, ["report", "--store", str(workspace["store"])])
    assert code == 0
    assert sorted(item["document_id"] for item in out["documents"]) == sorted([loans, parking])

    code, out, _ = _invoke(capsys, ["report", "--store", str(workspace["store"]), "--document-id", loans])
    assert code == 0
    assert out["document"]["document_id"] == loans
    assert [page["pdf_page"] for page in out["pages"]] == [1]
    assert out["pages"][0]["status"] == "OK"
    assert out["structure"]["units_by_type"].get("paragraph", 0) >= 1


def test_evaluate_runs_the_development_split_and_records_the_run(workspace, capsys):
    loans = _ingest(capsys, workspace, workspace["loans_pdf"])
    code, out, err = _invoke(
        capsys,
        [
            "evaluate",
            "--store",
            str(workspace["store"]),
            "--document-id",
            loans,
            "--gold",
            str(workspace["gold"]),
            "--split",
            "dev",
            "--output-dir",
            str(workspace["runs"]),
            "--run-id",
            "cli-dev-1",
        ],
    )
    assert code == 0, err
    assert out["split"] == "dev"
    assert out["final_run"] is False
    assert out["record_count"] == 1
    assert out["banner"].startswith("Synthetic test set")
    assert out["annotators"] == ["cli-test"]
    run_file = Path(out["run_file"])
    assert run_file == workspace["runs"] / "cli-dev-1.json"
    assert json.loads(run_file.read_text(encoding="utf-8"))["run_id"] == "cli-dev-1"
    with Store.open(workspace["store"]) as store:
        assert store.read_evaluation("cli-dev-1") is not None


def test_a_held_out_run_needs_the_final_flag_and_then_runs_once(workspace, capsys):
    loans = _ingest(capsys, workspace, workspace["loans_pdf"])
    base = [
        "evaluate",
        "--store",
        str(workspace["store"]),
        "--document-id",
        loans,
        "--gold",
        str(workspace["gold"]),
        "--split",
        "heldout",
        "--output-dir",
        str(workspace["runs"]),
    ]
    code, out, err = _invoke(capsys, base)
    assert code == 1 and out is None
    assert "--final-run" in err["error"]["message"]
    assert not workspace["runs"].exists() or not any(workspace["runs"].iterdir())

    code, out, err = _invoke(capsys, [*base, "--final-run", "--run-id", "cli-final-1"])
    assert code == 0, err
    assert out["split"] == "heldout"
    assert out["final_run"] is True
    assert out["record_count"] == 1


def test_evaluate_refuses_a_gold_file_whose_quotations_are_on_another_document(workspace, capsys):
    _ingest(capsys, workspace, workspace["loans_pdf"])
    parking = _ingest(capsys, workspace, workspace["parking_pdf"])
    code, out, err = _invoke(
        capsys,
        [
            "evaluate",
            "--store",
            str(workspace["store"]),
            "--document-id",
            parking,
            "--gold",
            str(workspace["gold"]),
            "--split",
            "dev",
            "--output-dir",
            str(workspace["runs"]),
            "--run-id",
            "cli-wrong-doc",
        ],
    )
    assert code == 1 and out is None
    assert err is not None
    assert not (workspace["runs"] / "cli-wrong-doc.json").exists()


def test_ask_writes_utf8_json_when_standard_output_is_a_file(tmp_path, capsys):
    pdf = _pdf(tmp_path / "loans.pdf", LOANS_SENTENCE)
    store = tmp_path / "store.sqlite"
    extracted = tmp_path / "extracted"
    code = main(["ingest", str(pdf), "--store", str(store), "--extracted-root", str(extracted)])
    assert code == 0
    document_id = json.loads(capsys.readouterr().out)["document_id"]

    answer_file = tmp_path / "answer.json"
    with answer_file.open("wb") as handle:
        completed = subprocess.run(
            [sys.executable, "-m", "app.api", "ask", "--store", str(store), "--document-id", document_id, CAFE_QUESTION],
            cwd=REPO_ROOT,
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
            timeout=300,
        )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    text = answer_file.read_bytes().decode("utf-8")  # a code-page encoding would fail here
    payload = json.loads(text)
    assert payload["question"] == CAFE_QUESTION
    assert payload["status"] == "INSUFFICIENT_EVIDENCE"
    assert "café" in text
