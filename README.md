# VeritasQA

**Ask a question about a PDF and get the exact sentence it came from, with its page number, or an honest "not enough evidence."**

VeritasQA is a document question-answering engine built on one rule: **no evidence, no answer.** It finds candidate passages, checks each one against the stored page, and refuses when the evidence is missing, ambiguous, contradictory or unreliable. It uses no language model, no embeddings and no vector database, so the same input always gives the same output.

- **Quotes, not paraphrases.** Every accepted answer comes with the exact sentence and its page, and with its section where the document has one.
- **Refuses rather than guesses.** Every refusal has a status and a reason.
- **Measured, not claimed.** Results are reported on public documents, with their limits. See [Results](#results).
- **Tested.** 1,341 tests passed and 1 was skipped in the project environment (the skip needs the optional Tesseract OCR program). A fresh environment with only `requirements.txt` gave 1,306 passed and 6 skipped (measured before three tests were added; not re-run). See [Quick start](#quick-start).

> **Status:** the core pipeline and the command-line tool are built and tested. The repository contains no private documents.

## Example

Real output from the current code, on a public NIST document (SP 800-63B-4):

```text
Question:  How many meters is the range limit that was chosen based on the maximum
           expected range of a Bluetooth connection?
Status:    ANSWERED
Answer:    240 meters
Quote:     "3The limit of 240 meters was chosen based on the maximum expected range of a Bluetooth connection."
Page:      50
```

The leading "3" is probably a footnote marker from the source PDF.

The same kind of question, on a topic the document does not cover (NIST CSF 2.0). Output from the current code:

```text
Question:  Does this document explain how to use blockchain or distributed ledger
           technology (DLT) for cybersecurity risk management?
Status:    INSUFFICIENT_EVIDENCE
Reason:    no retrieved sentence contains all of: document, explain, use, blockchain,
           distributed, ledger, technology, dlt, cybersecurity, risk, management
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

## Results

<a id="results"></a>

Measured once, on 74 development questions from four public NIST documents, with default settings. An assistant wrote the questions and a program checked them; no person has checked them by hand. The 23 held-out questions have not been run.

| Outcome | Count |
| --- | --- |
| Answered, and fully correct | 1 |
| Answered, with the right passage cited, but the wording did not match the expected text | 2 |
| Refused, although the document answers the question | 61 |
| Refused, correctly, because the document does not answer the question | 10 of 10 |
| Answered, although the document does not answer the question | 0 |

Answers are scored by exact text, so a correct fact in different words counts as wrong. That is a deliberate choice.

One private document, which is not published here, was measured the same way. The retrieval settings were swept on 32 development questions, and no setting gave an answer, so the defaults were kept. The 14 held-out questions were then run once. The system gave no answer to any of them, made no wrong answer, and correctly refused the one question the document does not answer. The questions were drafted by an assistant and partly checked, so this is not a claim of accuracy. The main limit is coverage: the system refuses most answerable questions.

The system is built to refuse rather than guess, and these results show that it refuses far too often. By design, it gives an answer only for numbers with units, percentages, money amounts, dates and periods, and permission or prohibition wording. Questions that begin with *what*, *who*, *where* or *which* return the matching passages without an answer. The acceptance rules are not tuned yet, because tuning needs labelled questions from a real document. Answering more often without giving wrong answers is the main open problem.

## Why no language model?

- **Traceable.** Each accepted answer points to a sentence on a page, and each decision lists the checks that produced it.
- **Repeatable.** The same input gives the same output, which makes failures reproducible.
- **Copied, not generated.** Answer spans are taken from the document's own text.

## How it works

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
| Command line | `app/api` | Ingests a PDF, asks questions, lists stored documents and runs evaluations. Prints JSON. |

## Quick start

<a id="quick-start"></a>

Requires Python 3.11 or later (tested with 3.12 on Windows), and a SQLite build with the FTS5 extension. No GPU, model download or API key is needed.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows; on macOS or Linux use .venv/bin/python
.venv/Scripts/python.exe -m pytest -q
```

The test suite creates its own synthetic PDFs. Some tests are skipped when an optional local document, the Tesseract OCR program or the optional TF-IDF packages (`requirements-experimental.txt`) are absent.

Command line, from the repository root. Each command prints one JSON object:

```bash
python -m app.api ingest my-document.pdf --store data/indexes/my-document.sqlite
python -m app.api ask --store data/indexes/my-document.sqlite --document-id DOCUMENT_ID "How many days is the limit for loans?"
python -m app.api report --store data/indexes/my-document.sqlite
python -m app.api evaluate --store data/indexes/my-document.sqlite --document-id DOCUMENT_ID --gold my-questions.jsonl --split dev
```

`ingest` prints the `document_id` to use in the other commands; replace `DOCUMENT_ID` with it. `ingest` writes the extraction outputs under `data/extracted/`, and `evaluate` writes its run file under `data/evaluations/runs/`. The gold file has the format of `tests/fixtures/p8_synthetic_gold.jsonl`. A held-out evaluation needs `--split heldout --final-run`. A command that completes exits with 0, and an abstention is a completed result. An error exits with 1 and prints one JSON object on standard error. `python -m app.api --help` lists the options.

Python interface:

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
    # The question below is the example from the top of this README. Replace it with your own.
    response = answer(
        store,
        extracted.document_id,
        "How many meters is the range limit that was chosen based on the maximum expected range of a Bluetooth connection?",
    )
    print(response.status.value)
    for span in response.answer_spans:
        print(span.text, "on page", span.pdf_page)
```

## Limitations

- **Answer types.** Only numbers with units, percentages, money amounts, dates and periods, and permission or prohibition wording get an answer span. Other questions return passages.
- **Matching is lexical.** Paraphrases are often missed. Synonym rules are supported, but none has been approved yet.
- **Scanned pages** need the optional Tesseract OCR program. That path is tested with a stub, not yet on a real scanned document.
- **Images and screenshots** are not read. A page that could not be verified is named in the answer's warnings, and nothing on it is accepted as evidence.
- **Tables.** Borderless tables are not detected. Table values come back as passages, not answers, and derived table rows are never quoted.
- **Tuning.** The page-quality thresholds and the acceptance settings are not tuned. On the private document, sweeping the retrieval settings changed nothing, so the defaults were kept.
- **Scope of results.** The results above describe four public documents only. Two documents in one store are tested with small synthetic PDFs, and no answer crosses between them.

## Roadmap

- Answer coverage. On the private document the system answered no question, so the next work is the answer types and the page-quality rules (reading order, tables and text inside images), followed by a new one-time test.
- A licence (see below).

## Documents

- [`docs/SPEC.md`](docs/SPEC.md): requirements, constraints, phases and the definition of done.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): design, data contracts, dependencies, risks and limitations.
- [`docs/SETUP.md`](docs/SETUP.md): environment setup and the validation record.
- [`PROGRESS.md`](PROGRESS.md): the project log, with phase status, decisions and open questions.

## Licence

No licence has been chosen yet. The PDF library the project uses, PyMuPDF, is licensed under AGPL-3.0 or sold under a commercial licence, so the choice needs care. Until a licence is added, the code is visible but reuse is not granted.
