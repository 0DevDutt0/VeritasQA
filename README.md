# VeritasQA
Evidence-First Document Intelligence

VeritasQA answers questions about a PDF using only text that exists in that PDF. When the evidence does not support an answer, it abstains and says why.

**No evidence, no answer.** VeritasQA is a deterministic, extractive question-answering system. It has no generative model, no hosted LLM API, no embedding model and no vector database, and V1 uses no PyTorch (D17). Every accepted answer carries an exact quotation with its page and section, and every decision records the checks that produced it.

> **Status:** Phases P0 to P5 are complete, including the deterministic V1 revision and the cleanup of the historical GPU, model and NLP layers (2026-11-04). Question analysis and extractive selection (P5) produce verbatim candidate passages and rule-determined answer spans. They do not decide support, which is for verification (P6) and the decision phase (P7). Ingestion (P1), structure (P2), storage with exact phrase search (P3) and BM25 candidates with reviewed-rule expansion (P4) are complete on synthetic and public documents. The real-document checks are blocked until the owner's PDF is supplied. P6 (evidence verification and citations) is next. See [`PROGRESS.md`](PROGRESS.md) for what is done, what is blocked and what is next.

## Documents

- [`docs/SPEC.md`](docs/SPEC.md): the engineering specification (requirements, hard constraints, phases, definition of done). Its body is verbatim; its header notes the V1 precedence.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): design, the V1 revision (§1A), data contracts, the dependency plan, risks and limitations
- [`PROGRESS.md`](PROGRESS.md): handoff file with phase status, blockers, decisions, the dependency inventory and the cleanup proposal
- [`docs/SETUP.md`](docs/SETUP.md): the V1 environment setup, the lock regeneration procedure and the validation record

## Quick start

Requires Python 3.11 or later with SQLite built with FTS5 (the startup check reports it if missing).

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows (Git Bash / PowerShell)
.venv/Scripts/python.exe -m pytest -q
```

The V1 baseline needs no GPU, no PyTorch and no model. The test suite generates its own synthetic PDFs. It does not need the owner's document. The optional TF-IDF group is described in [`docs/SETUP.md`](docs/SETUP.md). V1 does not need it.

## Principles

1. Evidence before answers.
2. Deterministic processing wherever practical.
3. Source provenance at every stage.
4. Conservative acceptance and mandatory abstention.
5. Measured results only. No accuracy or "zero hallucination" claim is made without a measured evaluation.

## Limitations

- The owner's ~100-page PDF is not yet included, so no result on the real document exists yet.
- Tesseract OCR is optional and is not installed on the development machine.
- Retrieval is lexical. Synonyms are limited to reviewed rules, and paraphrases are missed by design (D17).
- PyMuPDF is licensed AGPL-3.0 or commercially. Check the licence before distributing.

Full details are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §8.
