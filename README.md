# VeritasQA
Evidence-First Document Intelligence

VeritasQA answers questions about a PDF using only text that exists in that PDF. When the evidence does not support an answer, it abstains and says why.

**No evidence, no answer.** VeritasQA is an extractive, auditable question-answering system. It has no generative model, no hosted LLM API and no vector database. Every accepted answer carries an exact quotation with its page and section, and every decision records the checks that produced it.

> **Status:** Phase P0 (foundation) and the environment phase P0-ENV (CUDA, optional packages and pinned model artifacts) are complete, with limitations. Ingestion, retrieval, verification and evaluation are being built phase by phase. See [`PROGRESS.md`](PROGRESS.md) for what is done, what is blocked and what is next.

## Documents

- [`docs/SPEC.md`](docs/SPEC.md): the engineering specification (requirements, hard constraints, phases, definition of done)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): design, data contracts, dependency rationale, risks and limitations
- [`PROGRESS.md`](PROGRESS.md): handoff file with phase status, blockers, decisions and exit criteria
- [`docs/SETUP.md`](docs/SETUP.md): environment setup, the optional GPU and experimental groups, model artifacts and validation

## Quick start

Requires Python 3.11 or later with SQLite built with FTS5 (the startup check reports it if missing).

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows (Git Bash / PowerShell)
.venv/Scripts/python.exe -m pytest -q
```

The baseline needs no GPU, no PyTorch and no model. The test suite generates its own synthetic PDFs. It does not need the owner's document. The optional CUDA and NLP groups are described in [`docs/SETUP.md`](docs/SETUP.md).

## Principles

1. Evidence before answers.
2. Deterministic processing wherever practical.
3. Source provenance at every stage.
4. Conservative acceptance and mandatory abstention.
5. Measured results only. No accuracy or "zero hallucination" claim is made without a measured evaluation.

## Limitations

- The owner's ~100-page PDF is not yet included, so no result on the real document exists yet.
- Tesseract OCR is optional and is not installed on the development machine.
- PyMuPDF is licensed AGPL-3.0 or commercially. Check the licence before distributing.

Full details are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §8.
