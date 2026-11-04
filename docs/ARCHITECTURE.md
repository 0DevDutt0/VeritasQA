# VeritasQA Architecture

Status: P0 (foundation). This document is the design reference. The phase-by-phase execution plan and completion status are in [`PROGRESS.md`](../PROGRESS.md). The authoritative requirements are in [`SPEC.md`](SPEC.md); section references below use `SPEC §n`.

## 1. Purpose and non-goals

VeritasQA answers questions about a supplied PDF using only text that exists in that PDF. If the evidence does not support an answer, it abstains and says why (`SPEC` core principle: *no evidence, no answer*).

Non-goals for V1: any generative model or hosted LLM API, a vector database, Docker, cloud services, a web UI. The optional CLI arrives in P10 (`SPEC §14`).

## 2. Pipeline and package map

| Pipeline stage (SPEC §3) | Package | Phase |
| --- | --- | --- |
| Ingestion, extraction, quality validation | `app/ingestion` | P1 |
| Structure reconstruction, evidence segmentation | `app/document_structure` | P2 |
| Shared text normalization (reversible) | `app/common/text.py` | P2 |
| Storage and FTS5 availability check | `app/storage` | P0 (check), P3 (schema) |
| Indexing | `app/indexing` | P3 |
| Query processing | `app/question_processing` | P5 |
| Retrieval (phrase, BM25, expansion) | `app/retrieval` | P3, P4 |
| Evidence selection | `app/evidence` | P5 |
| Verification | `app/verification` | P6 |
| Conflict detection | `app/conflict` | P7 |
| Decision and abstention, response model | `app/decision` | P7 |
| Evaluation harness and metrics | `app/evaluation` | P8 |
| CLI (optional adapter) | `app/api` | P10 |

Packages are created in the phase that first needs them. Empty placeholder modules are not committed (`SPEC §15`: no placeholder modules).

Shared primitives that already exist:

- `app/common/errors.py`: `VeritasQAError` (base) and `StorageError`. Phase-specific subclasses are added where first raised.
- `app/common/files.py`: UTF-8 read/write helpers for text and JSON. Every file VeritasQA reads or writes uses them, so Windows' cp1252 default never applies. Output uses LF newlines.
- `app/storage/fts5.py`: `ensure_fts5_available()` and `fts5_available()`. They probe FTS5, phrase queries and `bm25()` on a private in-memory database and raise `StorageError` when any is missing.

## 3. Data contracts

These contracts are fixed now so that later phases can rely on them.

**Document identity.** `document_id = "doc-" + first 16 hex chars of SHA-256(file bytes)`. It is stable across renames and changes only when the content changes. Every table and query is scoped by `document_id` (`SPEC §3C`, multi-document readiness).

**Page indices.** `pdf_page` is the 1-based physical page index (PyMuPDF's 0-based index plus one). `printed_page` is the page label from the PDF (`page.get_label()`), or `null`. The two are never conflated. Citations use `pdf_page`.

**Immutable source text.** `pages.raw_text` is exactly what the extractor produced for that page, in reading order. Nothing downstream edits it. `source_start` and `source_end` are character offsets into that page's `raw_text`, half-open (`raw_text[source_start:source_end]` is the quotation).

**Evidence IDs.** `evidence_id = "{document_id}:p{pdf_page:04d}:u{ordinal:04d}"`, where `ordinal` is the unit's position in page reading order. Identical input and identical extractor version give identical IDs.

**Three representations (`SPEC §2`, `§3B`).**

1. `raw_text`: the immutable source text. All quotations and verification checks read this.
2. `index_text`: a normalized derivative used only for FTS5 indexing and query matching.
3. Structured metadata: page, section, parent, neighbours, bounding box, content type and quality status.

**Reversible normalization.** `normalize_with_map(raw)` returns the normalized text plus a per-character map back to raw offsets (planned in P2). Each NFKC-normalized character maps to the raw character it came from. Any index hit can therefore be resolved to exact raw offsets. Index normalization can cause a miss, but it can never create evidence, because verification checks only raw text.

**Extraction quality states.**

- Page status: `OK`, `WARNING`, `SCANNED` (image-only; needs OCR), `OCR_TEXT` (text produced by OCR), `BLANK`, `GARBLED`, `SUSPICIOUS`.
- Evidence `quality_status`: `verified`, `warning`, `unverified`. OCR text and garbled or suspicious pages are `unverified` and can never support an ANSWERED decision on their own (`SPEC §1`, `§9 SOURCE_UNVERIFIED`).
- `extraction_method`: `native_text`, `ocr_tesseract`, `none`.

**Decision statuses (`SPEC §9`).** `ANSWERED`, `INSUFFICIENT_EVIDENCE`, `AMBIGUOUS_QUERY`, `CONFLICT`, `SOURCE_UNVERIFIED`, `PARTIAL`. Retrieval scores, verification results and decision reasons are kept in separate response sections (`SPEC §10`).

**Response contract.** A Pydantic model that mirrors `SPEC §10`, with validated enums and required fields. The model is planned for P7.

## 4. Retrieval principles (planned P3–P4)

- FTS5 `bm25()` returns smaller, more negative values for better matches. Candidates are sorted by `bm25() ASC`. The raw value is kept for audit and is never exposed as a probability (`SPEC §4`, `§9`). P0 tests pin this direction.
- Queries are never passed to FTS5 unquoted. Each query token is extracted by a fixed pattern and wrapped as a quoted FTS5 string. All values are bound as SQL parameters.
- The FTS5 `unicode61` tokenizer splits `3.5` into `3` and `5`. Phrase search therefore uses FTS5 for candidates and then a deterministic substring check on normalized text. Numbers, units and dates are checked again in verification (P6).
- Heading text sits in a separate FTS5 column so its weight can be tuned (P4).
- Reciprocal Rank Fusion is not implemented. It is added only if a measured benchmark shows a gain (`SPEC §4`).
- Candidate depth K is configurable. Recall is measured at several K values; top-3 is never assumed sufficient.

## 5. Verification and decision principles

- Exact quotation existence proves **source integrity only**. It never proves that a passage answers a question (`SPEC §7`).
- Each question type has an explicit list of required checks. Any required check that fails or stays unresolved leads to abstention (`SPEC §9`).
- Acceptance gates are explicit booleans in a configuration file (for example `require_negation_validation = true`). They are not similarity-score thresholds. Calibration happens only on the development split, and the held-out split is used once (`SPEC §9`, `§11`).
- Conflicts are never resolved silently. Precedence applies only when the document states it explicitly (`SPEC §8`).

## 6. Storage schema (planned P3)

```
documents(document_id PK, source_name, sha256, page_count, pipeline_version, created_at)
pages(document_id, pdf_page, printed_page, width, height, extraction_method,
      quality_status, warnings_json, raw_text, PK(document_id, pdf_page))
sections(section_id PK, document_id, level, title, parent_section_id, start_page)
source_locations(location_id PK, document_id, pdf_page, source_start, source_end,
                 x0, y0, x1, y1)
evidence_units(evidence_id PK, document_id, location_id, pdf_page, printed_page,
               section_id, parent_id, prev_id, next_id, content_type, ordinal,
               raw_text, index_text, extraction_quality)
table_cells(evidence_id PK, table_id, row_index, col_index,
            row_header, col_header, caption)
evidence_fts USING fts5(index_text, heading_text,
                        evidence_id UNINDEXED, document_id UNINDEXED)
evaluations(run_id PK, created_at, split, config_json, metrics_json, dataset_sha256)
```

Every write uses parameterized SQL. The FTS5 table is queried only through bound parameters.

## 7. Dependencies and rationale

| Package | Pin | Role | Notes |
| --- | --- | --- | --- |
| PyMuPDF | `1.26.6` | Primary text, block, span and bbox extraction; page rendering | 1.26.6 declares no dependencies. The 2.x line pulls in onnxruntime, numpy, networkx, pymupdf4llm and pymupdf_layout, which the baseline does not need. **AGPL-3.0 or commercial licence; review before distributing.** |
| pdfplumber | `0.11.10` | Table detection and cell geometry (secondary) | Pulls in pdfminer.six and pypdfium2. |
| pydantic | `2.14.2` | Typed data contracts and response model | |
| pytest | `9.2.0` | Test runner | Dev dependency. |
| sqlite3 (stdlib) | Python 3.12.10 bundles SQLite 3.49.1 | Persistence, FTS5, BM25 | Availability checked at startup. |

Deliberately excluded for V1: numpy, scikit-learn (TF-IDF is an experiment only), spaCy/NLTK, FastAPI, any vector database, any LLM SDK. Each would need a benchmark or a concrete requirement before it is added (`SPEC §4`, `§13`).

**Tesseract OCR** is an external binary, not a Python dependency. The OCR adapter (P1) calls the `tesseract` CLI with an argument list (no shell) and works only when the binary is on PATH. On this machine it is **not installed** (see B2 in `PROGRESS.md`).

## 8. Risks, assumptions and limitations

- **No real document yet.** Development uses synthetic PDFs that the tests generate. Any measured result from them describes the pipeline, not the owner's document. Definition-of-Done items 1 and 9 (`SPEC §16`) need the owner's PDF and manually annotated gold data (blockers B1 and B3).
- **OCR is unverified on this machine.** Tesseract is not installed. OCR code paths are guarded and tested with a stub, and the real-binary tests are marked `requires_tesseract` and skipped when the binary is absent.
- **Reading order is heuristic.** Multi-column and irregular layouts can be misordered. The extractor flags suspected misordering as a warning and never assumes the extracted order is visual order (`SPEC §3A`).
- **Question understanding is rule-based.** Arbitrary natural language will not be understood. Unsupported or ambiguous questions must abstain (`SPEC §5`).
- **Licence risk.** PyMuPDF's AGPL terms apply to distribution and network use. The owner should confirm this is acceptable for a public repository.
- **Public repository.** The repository is public (anonymous `git ls-remote` succeeds). Source PDFs are git-ignored. Gold annotations under `data/evaluations/gold/` are tracked by default, so they become public; the owner must confirm this (open question Q2 in `PROGRESS.md`).
- **Platform.** Development is on Windows 11 with Git Bash and PowerShell. Tests write only to pytest temporary directories.

## 9. Reproducible setup

```bash
# from the repository root, using any Python 3.11+ interpreter
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows (Git Bash)
.venv/Scripts/python.exe -m pytest -q                         # run the test suite
```

The project venv used during development lives at `VeritasQA/` in the repository root. It is git-ignored and is not part of the project. The dependency pins in `requirements.txt` were validated in a clean venv (see `PROGRESS.md`, P0).
