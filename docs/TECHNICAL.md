# VeritasQA: technical guide

The overview and the results are in the [README](../README.md). This page has the setup, the commands, the Python interface and the detailed limits.

## Requirements

- Python 3.11 or later (tested with 3.12 on Windows).
- A SQLite build with the FTS5 full-text extension.
- No GPU, model download or API key.

## Set up and run the tests

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows; on macOS or Linux use .venv/bin/python
.venv/Scripts/python.exe -m pytest -q
```

- The latest full run gave 1,387 passed and 1 skipped. The skipped test needs the optional Tesseract OCR program.
- The tests create their own synthetic PDFs. Some tests are skipped when an optional local document, the Tesseract program or the optional TF-IDF packages (`requirements-experimental.txt`) are absent.
- A fresh environment built only from `requirements.txt` was measured earlier, before the latest tests were added (1,306 passed, 6 skipped). It has not been run since.

## Command line

Run from the repository root. Each command prints one JSON object.

```bash
python -m app.api ingest my-document.pdf --store data/indexes/my-document.sqlite
python -m app.api ask --store data/indexes/my-document.sqlite --document-id DOCUMENT_ID "How many days is the limit for loans?"
python -m app.api report --store data/indexes/my-document.sqlite
python -m app.api evaluate --store data/indexes/my-document.sqlite --document-id DOCUMENT_ID --gold my-questions.jsonl --split dev
python -m app.api compare --store data/indexes/my-document.sqlite --document-id NEW_DOCUMENT_ID --against OLD_DOCUMENT_ID
```

- `ingest` prints the `document_id` to use in the other commands, and writes the extraction outputs under `data/extracted/`.
- If an earlier version with the same file name is already in the store, `ingest` compares the two and adds the result as the `qa` field. `--against DOCUMENT_ID` names the earlier version when several match. `--report-dir` sets where the text report goes (default `data/reports/`, git-ignored).
- `compare` compares two documents already in the store, without ingesting again.
- `evaluate` writes its run file under `data/evaluations/runs/`. A held-out evaluation needs `--split heldout --final-run`. The evaluation files are described in `docs/ARCHITECTURE.md` §17.
- A command that completes exits with 0, and an abstention is a completed result. An error exits with 1 and prints one JSON object on standard error. `python -m app.api --help` lists the options.

## Python interface

```python
from datetime import datetime, timezone
from pathlib import Path

from app.decision.engine import answer
from app.document_structure import build_structure
from app.ingestion.extract import extract_document
from app.storage import Store

pdf = Path("my-document.pdf")  # a text-based PDF you have the right to use
extracted = extract_document(pdf, out_root=Path("data/extracted"))
structure = build_structure(extracted, pdf)

created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with Store.open(Path("data/indexes/my-document.sqlite")) as store:
    store.write_document(extracted, structure, created_at=created)
    # Replace the question with your own.
    response = answer(
        store,
        extracted.document_id,
        "How many meters is the range limit that was chosen based on the maximum expected range of a Bluetooth connection?",
    )
    print(response.status.value)
    for span in response.answer_spans:
        print(span.text, "on page", span.pdf_page)
```

## Statuses

| Status | Meaning |
| --- | --- |
| `ANSWERED` | The answer, with its exact quotation and page, and its section where the document has one. |
| `PARTIAL` | Some parts of a multi-part question are answered; the others are not. |
| `INSUFFICIENT_EVIDENCE` | No passage supports an answer. |
| `AMBIGUOUS_QUERY` | The question cannot be searched as written, or the document gives different values that depend on scope or date. Nothing is chosen. |
| `CONFLICT` | Two passages disagree. Both are shown, and neither is chosen. |
| `SOURCE_UNVERIFIED` | The page's text quality cannot be trusted, so nothing is accepted from it. |

## Document comparison

When a new version of a PDF is uploaded, the comparison reads the stored text of both versions and aligns their pages, so one inserted page does not make every later page look changed. It reports identical, changed, moved, added, removed and not comparable pages, with the changed words and the page numbers on both sides. The full rules are in `docs/ARCHITECTURE.md` §20.

Limits: the comparison is text only; a printed page number that changes after an inserted page shows as a changed word; a page that moved and also changed is shown as removed and added; a page with no readable text is not comparable.

## How the code is organised

| Stage | Package | What it does |
| --- | --- | --- |
| Ingestion | `app/ingestion` | Reads each page and rates its quality. Flags hidden text, scanned pages and damaged files. |
| Structure | `app/document_structure` | Rebuilds sections, paragraphs, lists and tables, keeping the page and position of each passage. |
| Storage | `app/storage` | SQLite with full-text search (FTS5), and a stored copy of every page. |
| Retrieval | `app/retrieval` | Ranks candidate passages (BM25) and checks exact phrases. |
| Question analysis and evidence | `app/question_processing`, `app/evidence` | Splits the question into parts, finds the passages, and gives an answer span only for supported types. |
| Verification | `app/verification` | Re-checks each candidate: exact quotation, location, value, subject, negation, conditions, source quality and more. |
| Decision | `app/decision`, `app/conflict` | Applies the acceptance rules, shows conflicts and chooses the status. |
| Evaluation | `app/evaluation`, `app/benchmark` | Validates question sets, computes metrics, and runs parameter sweeps on development data only. |
| Document comparison | `app/comparison` | Compares a new version of a document with the earlier one, page by page (`docs/ARCHITECTURE.md` §20). |
| Command line | `app/api` | Ingests a PDF, asks questions, compares versions, lists stored documents and runs evaluations. Prints JSON. |

## Limitations

- **Answer types.** Only numbers with units, percentages, money amounts, dates and periods, and permission or prohibition wording get an answer span. Other questions return passages.
- **Matching is lexical.** Paraphrases are often missed. Synonym rules are supported, but none has been approved yet.
- **Scanned pages and images.** No OCR is used, and images and screenshots are not read. A page that could not be verified is named in the answer's warnings, and nothing on it is accepted as evidence.
- **Tables.** Borderless tables are not detected. Table values come back as passages, not answers, and derived table rows are not quoted.
- **Tuning.** The page-quality thresholds and the acceptance settings are not tuned. On the private document, sweeping the retrieval settings changed nothing, so the defaults were kept.
- **Scope of results.** The published results describe four public documents only. Two documents in one store are tested with small synthetic PDFs, and no answer crosses between them.
