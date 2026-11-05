# VeritasQA Architecture

Status: P0 (foundation), revised 2026-11-04 by decision D17 to a deterministic, LLM-free and embedding-free V1. P0-CLEAN (2026-11-04) removed the historical GPU and model layers. This document is the design reference. The phase-by-phase execution plan and completion status are in [`PROGRESS.md`](../PROGRESS.md). The authoritative requirements are in [`SPEC.md`](SPEC.md); section references below use `SPEC §n`. Where SPEC §4 or §13 differ from the V1 plan, §1A and D17 govern.

## 1. Purpose and non-goals

VeritasQA answers questions about a supplied PDF using only text that exists in that PDF. If the evidence does not support an answer, it abstains and says why (`SPEC` core principle: *no evidence, no answer*). The V1 objective is maximum factual precision and minimum incorrect accepted answers. Recall is measured and reported, never assumed.

Non-goals for V1 (D17): any generative model or hosted LLM API; any embedding model, sentence-transformer or other learned encoder; dense or vector retrieval; cross-encoder or other learned reranking; PyTorch or any CUDA dependency; any model download at run time; a vector database; Docker; cloud services; a web UI. The optional CLI arrives in P10 (`SPEC §14`).

## 1A. Revised V1 architecture (D17, 2026-11-04)

The owner's change of plans of 2026-11-04 makes V1 a purely deterministic, LLM-free and embedding-free system.

- **Precedence.** For V1, D17 in `PROGRESS.md` governs. Where SPEC §4 (sentence-transformer embeddings and cross-encoder reranking as optional later experiments) or SPEC §13 (spaCy and NLTK as recommended technologies) differ from D17, V1 follows D17. The SPEC body is unchanged (D18).
- **Determinism target.** The same PDF bytes, question and configuration give the same response. The answer path uses no random seed, no model inference and no network access.
- **Retained components and their phases:**

  | Component | Phase | Role |
  | --- | --- | --- |
  | PyMuPDF, pdfplumber | P1, P2 | Text, block, span and table extraction; page rendering |
  | Python preprocessing (`normalize_with_map`) | P2 | Reversible index-side normalization. Raw text stays immutable |
  | Structure-aware paragraph and table extraction | P2 | Sections, paragraphs, list parents, table cells with their headers |
  | SQLite FTS5 with BM25 | P3, P4 | Candidate retrieval. The raw score is never shown as a probability |
  | Exact phrase and identifier retrieval | P3, P4 | Phrase check on normalized text; identifiers such as `ABC-123` |
  | Controlled synonym and stemming rules | P4 | Recall only; versioned, query-time, logged (§4) |
  | Deterministic extractive answer selection | P5 | Candidate spans from source text; no paraphrase |
  | Source verification; context, negation and condition checks | P6 | Raw-text checks that decide acceptance |
  | Conflict detection and mandatory abstention | P7 | Conflicts exposed, never silently resolved |
  | pytest evaluation and regression testing | P8, P9a | Metrics, gold data, regression cases |
  | TF-IDF (optional experimental baseline) | P9a | Sparse lexical weighting. Benchmark only; not an embedding |
  | Tesseract OCR (optional fallback) | P1 | External binary. Not installed on this machine (B2) |

- **Removed from the V1 plan (D17).** Sentence-transformers and the embedding and cross-encoder models; dense and vector retrieval; reranking; PyTorch and CUDA; vector databases; generative LLMs; model downloads at run time.
- **Import target.** No V1 pipeline module imports torch, sentence_transformers, transformers, huggingface_hub, spacy, nltk or rapidfuzz. P0-CLEAN (2026-11-04) removed the two modules that imported torch or sentence-transformers lazily. `tests/unit/test_p0_dependencies.py` enforces the rule: it scans the requirement files, `pyproject.toml`, the imports under `app/`, and the modules that importing the package loads.

## 2. Pipeline and package map

| Pipeline stage (SPEC §3) | Package | Phase |
| --- | --- | --- |
| Ingestion, extraction, quality validation | `app/ingestion` | P1 |
| Structure reconstruction, evidence segmentation | `app/document_structure` | P2 |
| Shared text normalization (reversible) | `app/common/text.py` | P2 |
| Storage and FTS5 availability check | `app/storage` | P0 (check), P3 (schema) |
| Indexing (FTS5 population is part of the write path, so there is no separate package) | `app/storage` | P3 |
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
- The P0-ENV GPU and model modules (`app/common/device.py`, `app/common/models.py`) and scripts were removed in P0-CLEAN (2026-11-04). Their history is in git up to commit `e57c443`.

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

- Page status: `OK`, `WARNING`, `SCANNED` (image-only; needs OCR), `SCANNED_TEXT_LAYER` (image-dominated page whose text has an unknown origin; P1), `OCR_TEXT` (text produced by OCR), `BLANK`, `GARBLED`, `SUSPICIOUS`. The mapping to quality is in §10.
- Evidence `quality_status`: `verified`, `warning`, `unverified`. OCR text, text layers of unknown origin, and garbled or suspicious pages are `unverified` and can never support an ANSWERED decision on their own (`SPEC §1`, `§9 SOURCE_UNVERIFIED`).
- `extraction_method`: `native_text`, `ocr_tesseract`, `none`.

**Decision statuses (`SPEC §9`).** `ANSWERED`, `INSUFFICIENT_EVIDENCE`, `AMBIGUOUS_QUERY`, `CONFLICT`, `SOURCE_UNVERIFIED`, `PARTIAL`. Retrieval scores, verification results and decision reasons are kept in separate response sections (`SPEC §10`).

**Response contract.** A Pydantic model that mirrors `SPEC §10`, with validated enums and required fields. The model is planned for P7.

## 4. Retrieval principles (planned P3–P4)

- FTS5 `bm25()` returns smaller, more negative values for better matches. Candidates are sorted by `bm25() ASC`. The raw value is kept for audit and is never exposed as a probability (`SPEC §4`, `§9`). P0 tests pin this direction.
- Queries are never passed to FTS5 unquoted. Each query phrase is normalized and passed as one quoted FTS5 string, with its double quotes doubled (§12). All values are bound as SQL parameters.
- The FTS5 `unicode61` tokenizer splits `3.5` into `3` and `5`. Phrase search therefore uses FTS5 for candidates and then a deterministic substring check on normalized text. Numbers, units and dates are checked again in verification (P6).
- Heading text sits in a separate FTS5 column so its weight can be tuned (P4, §13).
- **BM25 statistics are per document (P4, D39).** `bm25()` runs on an index built from one document's body units (§13). Adding a second document to the store therefore leaves the first document's scores and ranking unchanged, as §1A requires.
- Reciprocal Rank Fusion is not implemented. It is added only if a measured benchmark shows a gain (`SPEC §4`).
- Candidate depth K is configurable. Recall is measured at several K values; top-3 is never assumed sufficient.
- **Controlled synonym and stemming rules (P4, D17, D38, D43).** Recall only. The rules live in `config/retrieval_rules.toml`, with the format and the expansion rules in §13. Each rule has an ID, a version, positive examples, counter-examples and a reviewer note. Expansion is query-time and one-way: a query term may add listed alternatives, and the index is never rewritten. Each expansion is recorded in the retrieval trace with its rule ID. Expanded matches only add candidates, and they are marked `expansion_only`. The entity, value, negation and condition checks (§5) run on raw text and cannot be satisfied by an expansion alone. No rule is approved in V1 (D43).
- **No stemming in the index for V1.** SQLite's FTS5 `porter` tokenizer exists in this build (SQLite 3.49.1): with it, the query `run` matches `running`. The tokenizer is fixed per FTS table, so it cannot be switched per query, and a stemmed index would need a second FTS table. It is not used unless the P4 regression set shows a need.
- **TF-IDF is an experiment, not a neural model.** scikit-learn TF-IDF is sparse lexical weighting over the same index text. It is benchmark-only (P9a), outside the acceptance path, and never shown as similarity or as an embedding.
- **No dense retrieval or reranking in V1.** Embeddings, vector search and cross-encoders are outside V1 (D17).

## 5. Verification and decision principles

- Exact quotation existence proves **source integrity only**. It never proves that a passage answers a question (`SPEC §7`).
- Each question type has an explicit list of required checks. Any required check that fails or stays unresolved leads to abstention (`SPEC §9`).
- Acceptance gates are explicit booleans in a configuration file (for example `require_negation_validation = true`). They are not similarity-score thresholds. Calibration happens only on the development split, and the held-out split is used once (`SPEC §9`, `§11`).
- Conflicts are never resolved silently. Precedence applies only when the document states it explicitly (`SPEC §8`).
- **Retrieval expansions never count as support.** A synonym or stem match can only add a candidate. The entity, value, negation and condition checks read raw text and must find the question's terms in it. An expansion that does not appear in the raw text leads to abstention, which is the intended conservative outcome. The owner decided on 2026-11-04 that reviewed rules never count toward acceptance (`PROGRESS.md`, D38). A rule-reached candidate is `expansion_only` and no check may accept it as support.

## 6. Storage schema (P3, revised)

P3 implements this schema in `app/storage/schema.py`. It is derived from the P2 models (`EvidenceUnit`, `Section`, `TableCell`, `StructureIssue`, `DocumentStructure`) and the P1 records (`ExtractedDocument`, `ExtractedPage`), so a structure read back from the store equals the one written. `PRAGMA user_version = 1` marks the schema, and `PRAGMA foreign_keys = ON` is set on every connection.

```
CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    page_count INTEGER NOT NULL CHECK (page_count >= 1),
    extractor_version TEXT NOT NULL,
    structure_version TEXT NOT NULL,
    pymupdf_version TEXT NOT NULL,
    pdfplumber_version TEXT NOT NULL,
    extraction_config_sha256 TEXT NOT NULL,
    structure_config_sha256 TEXT NOT NULL,
    issues_json TEXT NOT NULL,      -- document-level extraction issues (code, severity, detail)
    created_at TEXT NOT NULL        -- UTC, ISO 8601; the only column that differs between runs
);
CREATE TABLE pages (
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    pdf_page INTEGER NOT NULL CHECK (pdf_page >= 1),
    printed_page TEXT,
    width REAL NOT NULL,
    height REAL NOT NULL,
    rotation INTEGER NOT NULL,
    status TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    extraction_method TEXT NOT NULL,
    warnings_json TEXT NOT NULL,    -- the page's issues (code, severity, detail)
    raw_text TEXT NOT NULL,         -- immutable; every quotation is a slice of it
    raw_text_sha256 TEXT NOT NULL,
    PRIMARY KEY (document_id, pdf_page)
);
CREATE TABLE sections (
    section_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    position INTEGER NOT NULL,      -- index in the structure's section list
    level INTEGER NOT NULL CHECK (level >= 1),
    title TEXT NOT NULL,
    parent_section_id TEXT REFERENCES sections(section_id),
    start_pdf_page INTEGER NOT NULL,
    heading_id TEXT NOT NULL REFERENCES evidence_units(evidence_id),
    UNIQUE (document_id, position)
);
CREATE TABLE evidence_units (
    evidence_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    pdf_page INTEGER NOT NULL,
    printed_page TEXT,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    content_type TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    index_text TEXT NOT NULL,
    heading_text TEXT NOT NULL,
    section_id TEXT REFERENCES sections(section_id),
    parent_id TEXT REFERENCES evidence_units(evidence_id),
    prev_id TEXT REFERENCES evidence_units(evidence_id),
    next_id TEXT REFERENCES evidence_units(evidence_id),
    extraction_quality TEXT NOT NULL,
    body_retrieval INTEGER NOT NULL CHECK (body_retrieval IN (0, 1)),
    derived INTEGER NOT NULL CHECK (derived IN (0, 1)),
    table_id TEXT,
    row_index INTEGER,
    col_index INTEGER,
    row_header TEXT,
    col_header TEXT,
    caption TEXT,
    x0 REAL NOT NULL, y0 REAL NOT NULL, x1 REAL NOT NULL, y1 REAL NOT NULL,   -- the unit's box
    UNIQUE (document_id, pdf_page, ordinal),
    FOREIGN KEY (document_id, pdf_page) REFERENCES pages(document_id, pdf_page)
);
CREATE TABLE source_locations (
    location_id INTEGER PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    evidence_id TEXT NOT NULL REFERENCES evidence_units(evidence_id),
    span_index INTEGER NOT NULL CHECK (span_index >= 0),
    pdf_page INTEGER NOT NULL,
    source_start INTEGER NOT NULL CHECK (source_start >= 0),
    source_end INTEGER NOT NULL,
    UNIQUE (evidence_id, span_index),
    CHECK (source_start < source_end)
);
CREATE TABLE table_cells (
    evidence_id TEXT PRIMARY KEY REFERENCES evidence_units(evidence_id),
    table_id TEXT NOT NULL,
    row_index INTEGER NOT NULL CHECK (row_index >= 0),
    col_index INTEGER NOT NULL CHECK (col_index >= 0),
    row_header TEXT,
    col_header TEXT,
    caption TEXT
);
CREATE TABLE structure_issues (
    issue_id INTEGER PRIMARY KEY,   -- insertion order is the structure's issue order
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    pdf_page INTEGER NOT NULL,
    code TEXT NOT NULL,
    detail TEXT NOT NULL,
    FOREIGN KEY (document_id, pdf_page) REFERENCES pages(document_id, pdf_page)
);
CREATE VIRTUAL TABLE evidence_fts USING fts5(
    index_text, heading_text, evidence_id UNINDEXED, document_id UNINDEXED
);
CREATE TABLE evaluations (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    split TEXT NOT NULL,
    config_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL
);
```

**Changes from the first draft, and why.**
- `source_locations` holds one row per span, keyed by `evidence_id` and `span_index`. The first draft's `evidence_units.location_id` could point at one location, but a table row has several spans (§11). The bounding box is per unit (`EvidenceUnit.bbox`), so it sits on `evidence_units`, not on each span.
- `evidence_units` holds every field of `EvidenceUnit`, including the table fields of `table_row` units. Those rows have no `table_cells` record, so the first draft could not restore them.
- `sections.position` restores the section order exactly. `heading_id` is P2's pointer to the heading unit.
- `pages` keeps the page status, the raw-text hash and the page's issues. Page metrics that retrieval does not need (ink ratio, image coverage, column count and similar) stay in `extraction_report.json`, which remains their record.
- `structure_issues` keeps P2's issues, so a structure read back equals the one written.
- `table_cells` mirrors the cell units exactly as P2 emits them (§11). P3 checks the mirror before it writes.
- `documents` records the library versions and the P1 and P2 configuration hashes.

**Write rules.** Checked before the database is touched (`StorageIntegrityError`; nothing is written): every record names the same `document_id`; each page's `raw_text_sha256` matches its text; each unit's spans lie inside its page and reproduce its `raw_text` (`"\n".join(...) == raw_text`); evidence IDs and section IDs are unique; every reference (`section_id`, `parent_id`, `prev_id`, `next_id`, `heading_id`, the parent section) names a record of the same document; each table-cell record matches its unit.

**Transactions.** A document is written in one `BEGIN IMMEDIATE` transaction that includes its `evidence_fts` rows. A rewrite of the same `document_id` replaces the earlier rows and never duplicates FTS rows. Any failure rolls back, so the database keeps the previous content, or nothing for a first write. `PRAGMA defer_foreign_keys = ON` is set inside the transaction, because `prev_id`, `next_id`, `parent_id` and `heading_id` point both forward and backward.

**FTS population.** Only units with `body_retrieval = 1` enter `evidence_fts`. Header and footer units stay in `evidence_units` and never take part in body retrieval. Derived `table_row` units are indexed, because they carry the header-value pairs of a row (§11). Their `index_text` is generated, so P6 must never quote it.

Every write uses parameterized SQL. The FTS5 table is queried only through bound parameters, and every MATCH expression is built by the rules in §12.

## 7. Dependency plan (D17, after P0-CLEAN)

The V1 dependency plan is the baseline plus one optional group that the owner allowed. The lock `requirements-validated.txt` records the whole project venv. The pre-cleanup inventory (83 installed distributions, 2026-11-04) is classified in `PROGRESS.md` under P0-ENV, "Classification under D17". P0-CLEAN then removed the historical layers, as recorded there and in the P0-CLEAN section.

**Baseline (V1, necessary).** `requirements.txt`:

| Package | Pin | Role | Notes |
| --- | --- | --- | --- |
| PyMuPDF | `1.26.6` | Text, block, span and bbox extraction; page rendering (P1) | Declares no dependencies. The 2.x line pulls in onnxruntime, numpy, networkx, pymupdf4llm and pymupdf_layout. **AGPL-3.0 or commercial licence; review before distributing (Q4).** |
| pdfplumber | `0.11.10` | Table detection and cell geometry (P2) | Pulls in pdfminer.six, pypdfium2 and Pillow; pdfminer.six pulls in cryptography. |
| pydantic | `2.14.2` | Typed data contracts and the response model | |
| pytest | `9.2.0` | Test runner (dev) | |
| sqlite3 (stdlib) | Python 3.12.10 bundles SQLite 3.49.1 | Persistence, FTS5, BM25 | Availability checked at startup. |
| Tesseract OCR | external binary | OCR fallback (P1) | Not a Python dependency. Called as a CLI with an argument list, never through a shell. Not installed here (B2). |

The baseline closure is 20 distributions: the four pins above and 16 transitive packages. It contains no NumPy.

**Optional (`requirements-experimental.txt`; not in the baseline, and not imported by it).**

| Group | Packages | Status |
| --- | --- | --- |
| TF-IDF baseline | numpy 2.5.4 and scikit-learn 1.9.1, with their dependencies (listed in the lock) | Optional. Sparse lexical weighting, benchmark-only (P9a), outside the acceptance path, never an embedding. Installed in the project venv so that the P9a baseline can run. |

**Removed from the V1 plan.** P0-CLEAN (2026-11-04) removed these items from the project venv, the repository and the model folder. The owner's decision on Q6 removed spaCy, NLTK and rapidfuzz. D17 removed the rest.

| Item | Removed | Reason |
| --- | --- | --- |
| PyTorch and CUDA | torch 2.14.1+cu130, and the packages that only the removed layers needed (sympy, networkx, mpmath, filelock, fsspec) | Owner directive: CUDA is not required for the V1 retrieval and verification pipeline. |
| Embedding and reranking models | sentence-transformers, transformers, tokenizers, safetensors; the models all-MiniLM-L6-v2 and ms-marco-MiniLM-L6-v2 | Owner directive: no embeddings and no cross-encoders. |
| Model download tooling | huggingface-hub, hf-xet, httpx2, httpcore2, truststore, PyYAML; `scripts/download_models.py` | Only used to fetch the models above. |
| NLP and fuzzy matching (Q6) | spaCy 3.8.18, NLTK 3.10.4 with `punkt_tab`, rapidfuzz 3.14.6 | Owner decision Q6, 2026-11-04. P5 is planned as a deterministic, abbreviation-aware splitter. Approximate matching would accept inexact matches. |
| GPU device code and files | `app/common/device.py`, `app/common/models.py`, `requirements-gpu.txt`, `constraints-gpu.txt`, `.env.example`, the model manifests | Served only the removed layers. |
| Vector databases and generative LLMs | none installed | Excluded by SPEC §1 and the owner's directive. |

Under D17 the owner's direction defines the V1 plan. It supersedes the P0-ENV layering (D12, D13, D16) and the earlier exclusion list of P0.

**Tesseract OCR** is an external binary, not a Python dependency. The OCR adapter (P1) calls the `tesseract` CLI with an argument list (no shell) and works only when the binary is on PATH. It is not installed on this machine (see B2 in `PROGRESS.md`).

**Lock.** `requirements-validated.txt` lists the 27 pins of the project venv: the baseline and the optional group, each at its exact version. It is produced with `pip freeze --exclude pip` from a fresh venv, and it is never edited by hand. The procedure is in [`docs/SETUP.md`](SETUP.md) §4.

The pins in `requirements.txt` were validated in a clean venv in P0 and P0-ENV. They did not change under D17 or P0-CLEAN, and the V1 baseline was re-verified after each change (`PROGRESS.md`).

## 8. Risks, assumptions and limitations

- **No real document yet.** Development uses synthetic PDFs that the tests generate. Any measured result from them describes the pipeline, not the owner's document. Definition-of-Done items 1 and 9 (`SPEC §16`) need the owner's PDF and manually annotated gold data (blockers B1 and B3).
- **OCR is unverified on this machine.** Tesseract is not installed. OCR code paths are guarded and tested with a stub, and the real-binary tests are marked `requires_tesseract` and skipped when the binary is absent.
- **Reading order is heuristic.** Multi-column and irregular layouts can be misordered. The extractor flags suspected misordering as a warning and never assumes the extracted order is visual order (`SPEC §3A`).
- **Lexical recall is limited (D17).** Synonym coverage is limited to the reviewed rules. Paraphrases are missed by design, and abstention covers the misses. Stemming and synonym rules can over-match, so each rule must pass a false-match regression set (P4) before it is admitted.
- **Question understanding is rule-based.** Arbitrary natural language will not be understood. Unsupported or ambiguous questions must abstain (`SPEC §5`).
- **Licence risk.** PyMuPDF's AGPL terms apply to distribution and network use. The owner should confirm this is acceptable for a public repository.
- **Public repository.** The repository is public (anonymous `git ls-remote` succeeds). Source PDFs are git-ignored. Gold annotations under `data/evaluations/gold/` are tracked by default, so they become public; the owner must confirm this (open question Q2 in `PROGRESS.md`).
- **Historical code removed.** P0-CLEAN (2026-11-04) removed the GPU and model layers, the NLP packages, and the device and model tests. The deny-list test (`tests/unit/test_p0_dependencies.py`) now enforces the V1 rule. Run it before any claim that V1 is torch-free. Git history up to commit `e57c443` keeps the removed code.
- **Platform.** Development is on Windows 11 with Git Bash and PowerShell. Tests write only to pytest temporary directories.

## 9. Reproducible setup

```bash
# from the repository root, using any Python 3.11+ interpreter
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # V1 baseline (Windows, Git Bash)
.venv/Scripts/python.exe -m pytest -q                         # baseline test suite
```

The optional TF-IDF group is described in [`docs/SETUP.md`](SETUP.md). Only the baseline is part of V1 (D17). The project venv used during development lives at `VeritasQA/` in the repository root. It is git-ignored and is not part of the project. The lock `requirements-validated.txt` records the whole project venv, and [`docs/SETUP.md`](SETUP.md) §4 gives the procedure for regenerating it. The baseline pins were validated in a clean venv (see `PROGRESS.md`, P0, P0-REV and P0-CLEAN).

## 10. Ingestion contracts (P1)

Implemented in `app/ingestion`. Configuration is `config/default.toml`, section `[ingestion]`. `app/ingestion/config.py` loads it with Pydantic and rejects unknown keys. The thresholds are documented heuristics, not acceptance thresholds, and they are uncalibrated on a real document (B1).

**Entry points.** `validate_pdf(path, config) -> PdfFileInfo`. `extract_document(path, *, config=None, out_root=None, ocr_command=None) -> ExtractedDocument`. When `out_root` is given, the outputs are written under `out_root/<document_id>/`. Without it, nothing is written.

**Validation (`PdfRejectedError.code`).** `file_missing`, `file_empty`, `file_too_large` (`max_file_bytes`), `bad_header` (the first five bytes are not `%PDF-`), `cannot_open` (PyMuPDF refuses the file), `encrypted_requires_password` (`needs_pass` is true), `no_pages`. A file that opens without a password is accepted, even when its owner password restricts printing.

**Repairs and truncation.** MuPDF repairs broken files silently. The extractor reads `is_repaired` and the MuPDF message buffer (reset before the open, read after the page loop). A repaired document, or one with no `%%EOF` in its last `eof_tail_bytes` bytes, is recorded at document level and stamped as a WARNING on every page (`pdf_repaired`, `pdf_missing_eof`).

**Outputs.**

```
<out_root>/<document_id>/extraction_report.json   per-document report, without raw text
<out_root>/<document_id>/pages/p0001.txt          raw_text of each page: UTF-8, LF, no added newline
<out_root>/<document_id>/renders/p0001.png        renders of non-OK pages (inspection only)
```

The report has no timestamps and no absolute paths. The same bytes and configuration give a byte-identical report. `config_sha256` identifies the configuration used.

**Page record.** `pdf_page` (1-based), `printed_page` (the PDF label, or `null`), `width`, `height`, `rotation`, `status`, `quality_status`, `extraction_method` (`native_text`, `ocr_tesseract` or `none`), `visible_chars`, `hidden_chars`, `non_space_chars`, `image_coverage` (0 to 1), `ink_ratio` (only when measured), `table_count`, `column_count`, `reading_order` (`none`, `single_column` or `multi_column`), `reading_order_uncertain`, `issues`, `blocks`, `raw_text_path`, `raw_text_sha256` and `render_path`.

**Block record.** `block_no` (the PyMuPDF block that the lines came from; `-1` for OCR text), `role` (`body`, `header`, `footer`, `image` or `ocr`), `bbox`, `reading_index` and `column_index` (text roles only), `raw_start` and `raw_end` (half-open offsets into `raw_text`; `null` for images), and `lines`. A line has `bbox`, `raw_start`, `raw_end`, `text`, `spans` and `hidden_chars`. A span has `text`, `bbox`, `font`, `size`, `flags` and `bold` (`flags & 16`).

**Raw text assembly.** Header blocks come first, then body blocks in reading order, then footer blocks. The lines of a block are joined with `\n`, and blocks are joined with `\n\n`. A line is a run of spans in which each neighbour lies within `line_gap_em` font sizes, in either direction. Cells of a ruled table that share a baseline therefore sit on separate lines (for example, `3.5` on its own line). Lines, not PyMuPDF blocks, are the unit of ordering, because PyMuPDF can place the lines of two columns on one baseline inside one block. Consecutive lines that share a PyMuPDF block, a column and a band form one block. PyMuPDF's native order is never used as the reading order.

**Reading order.** A text line whose width is at least `wide_block_width_fraction` of the widest body-text extent is a full-width separator. The narrow lines between separators form a band. Within a band, lines are clustered into columns by horizontal overlap, read left to right and then top to bottom within each column. The page is flagged `reading_order_uncertain` for `overlapping_text` (two lines overlap by more than `overlap_area_fraction_max` of the smaller one), `narrow_gutter` (a column gap below `min_gutter_fraction` of the widest extent), or `wide_block_overlap` (a narrow line shares vertical extent with a full-width line). Ruled-table cells are read column by column, so a page with a table is a WARNING (`table_detected`), and P2 rebuilds the rows from the cells.

**Header and footer.** A line whose text, with digits replaced by `#`, appears in the top or the bottom `header_footer_band_fraction` of at least `max(2, ceil(pages / 2))` pages gets role `header` or `footer`. Its lines are excluded from the column clustering. They stay in `raw_text`, first for headers and last for footers.

**Hidden text layers.** `dict` spans do not expose the text render mode, so the extractor reads `page.get_texttrace()`. Characters whose `type` is 3 or 7 are invisible. Every page with invisible text stays below `OK`:
- an image-dominated page with any text is `SCANNED_TEXT_LAYER` (reason `hidden_text_layer` when some text is invisible);
- a page whose only text is invisible is `SUSPICIOUS` (`hidden_text_only`);
- a page whose invisible share of its text characters exceeds `hidden_text_share_max` (default 2%) is `SUSPICIOUS` (`hidden_text_share_high`);
- a smaller invisible share is `WARNING` (`hidden_text_present`);
- when the trace cannot be read, the page is `WARNING` (`text_render_mode_unknown`).

Each line records `hidden_chars`, the number of invisible glyphs whose centre lies in that line. P2 must treat a line with `hidden_chars > 0` as unverified and must not ground an answer on it (D20). Text that is invisible by colour (for example white text, render mode 0) is not detected by this trace.

**Page status and quality.**

| Status | Meaning | `quality_status` |
| --- | --- | --- |
| `OK` | Text passes every check | `verified` |
| `WARNING` | Usable but flagged: table, uncertain reading order, rotated page, invisible text beside visible text, repaired or truncated document, table check failure | `warning` |
| `SCANNED` | No text, image-dominated; OCR not run or produced no text | `unverified` |
| `OCR_TEXT` | Text produced by Tesseract | `unverified` |
| `SCANNED_TEXT_LAYER` | Image-dominated page with text of unknown origin | `unverified` |
| `BLANK` | No text and almost no ink at `blank_check_dpi` | `unverified` (no evidence) |
| `GARBLED` | Replacement, control or private-use characters above `garbled_char_ratio_max` | `unverified` |
| `SUSPICIOUS` | Letter ratio or single-letter token ratio unusual; text without visible glyphs; invisible share above `hidden_text_share_max`; or content without text | `unverified` |

Decision order: OCR text; then the no-text rules (image coverage, then ink); then the text rules (image coverage, invisible-only text, garbled, suspicious, warning, OK). Each non-OK status carries at least one issue that gives its reason.

**OCR.** Runs only when `ocr_mode = "auto"` and `tesseract` is on PATH, or when a command is passed explicitly (tests). It is an argument list with no shell. The language is validated against `^[A-Za-z0-9_+]+$`. Failure or empty output keeps the page `SCANNED` with `ocr_failed` or `ocr_no_text`. When OCR cannot run, the reason is `ocr_unavailable` (no binary) or `ocr_disabled` (mode `off`). OCR text has page-level coordinates only.

**Issue vocabulary.** An issue has a `code`, a `severity` (`info` or `warning`) and a `detail` that states the measured values. Only `warning` severity can change a page status. The codes are listed in `app/ingestion/models.py`.

## 11. Structure and provenance contracts (P2)

Implemented in `app/common/text.py` (normalization) and `app/document_structure/` (structure). Thresholds are in `config/structure.toml`, section `[structure]`, loaded by `app/document_structure/config.py` with Pydantic (`extra="forbid"`). They are documented heuristics, uncalibrated on a real document (D26). The file is separate from `config/default.toml`, so the P1 configuration and its tests do not change.

**Entry point.** `build_structure(extracted, pdf_path, *, config=None) -> DocumentStructure`. `extracted` is an `ExtractedDocument` with `raw_text` in memory (from `extract_document` or `load_outputs`). `pdf_path` is needed only for table geometry, which pdfplumber reads. Its SHA-256 must equal `extracted.sha256`, or the call raises `StructureError`. The PDF is never read for text: all evidence text comes from P1's `raw_text`.

**Normalization.** `normalize_with_map(raw) -> NormalizedText`. `NormalizedText.text` is the index form. `NormalizedText.spans[i]` is the half-open raw range `(start, end)` that output character `i` came from. `raw_range(start, end)` maps an index range back to raw offsets.
- Processing unit: a base character with the combining marks that follow it. The unit is translated and NFKC-normalized as one string, and every output character maps to the unit's whole raw range. Composition therefore works across combining marks.
- Translation: curly quotes to `'` and `"`; dash variants (U+2010 to U+2015, U+2212) to `-`. Deleted outright: U+00AD (soft hyphen), U+200B, U+200E, U+200F and U+FEFF.
- Whitespace: newlines and other whitespace become one space, and runs of spaces collapse to one. The surviving space maps to its own raw range.
- Dehyphenation (index text only): a hyphen (`-`, U+2010, U+2011 or U+00AD) followed by one `\n` and a lowercase letter is removed together with the newline.
- Guarantees: spans are monotonic, and the index text is a pure function of the raw text.

**Document structure.** `DocumentStructure(document_id, sections, units, table_cells)`.
- `Section(section_id, document_id, level, title, parent_section_id, start_pdf_page, heading_id)`. Section IDs are `{document_id}:s{n:04d}` in document order, starting at 1.
- `EvidenceUnit` fields: `evidence_id`, `document_id`, `pdf_page`, `printed_page`, `ordinal`, `content_type`, `raw_text`, `source_spans`, `index_text`, `heading_text`, `section_id`, `parent_id`, `prev_id`, `next_id`, `bbox`, `table_id`, `row_index`, `col_index`, `row_header`, `col_header`, `caption`, `extraction_quality`, `body_retrieval`, `derived`.
- `content_type` is one of `heading`, `paragraph`, `list_item`, `caption`, `footnote`, `table_cell`, `table_row`, `header`, `footer`, `page_text`.
- `ordinal` is the unit's position on its page, counted from 1. `evidence_id` follows ARCHITECTURE §3 (D5).
- `source_spans` are half-open offsets into the page's `raw_text`. The unit's `raw_text` is the newline join of its spans. Lines whose raw gap holds only whitespace share one span, so a paragraph that crosses P1 blocks stays one verbatim slice, with the page's own separator inside it. Only table cells and rows can have several spans, because their lines are not adjacent. A single-span unit satisfies `raw_text == page_raw_text[start:end]`. P3 needs one `source_locations` row per span (ARCHITECTURE §6).
- `index_text` is a normalized derivative of `raw_text`, used only for retrieval. A table cell's `index_text` is `caption | row_header | col_header | value` (empty parts skipped), so a number is never indexed without its row and column.
- `heading_text` is the chain of section titles, joined with ` > `.
- `extraction_quality` inherits the page's quality (`verified`, `warning` or `unverified`). It is forced to `unverified` when any line of the unit has `hidden_chars > 0` (D20).
- `body_retrieval` is `false` for `header` and `footer` units. They are kept and never deleted.
- `derived` is `true` only for `table_row` units. Their `raw_text` is the verbatim cell text in column order, so their spans point at real text. Their `index_text` is generated (`caption | row_header | col_header = value; ...`). P6 must never quote a derived `index_text`.
- `prev_id` and `next_id` chain every unit of the document in page order, across pages, including derived rows.

**Pages.** Structure is built only for `verified` and `warning` pages.
- A page of any other status produces one `page_text` unit per P1 text block (`raw_text` of the block, `extraction_quality = unverified`). It has no sections, headings, tables or lists. Its header and footer blocks keep their roles.
- Image blocks produce no units.
- Units are emitted in P1's block order: headers, then body blocks, then footers.

**Body size and headings.**
- Body size is the character-weighted mode of span sizes, quantized to 0.5 pt, over body lines with at least `body_stat_min_chars` letters.
- A candidate heading is a body line that is (a) at least `heading_size_delta` pt above body size, or (b) bold at body size, with at most `heading_max_chars` characters, not ending in `.`, `,` or `;`, and not vertical (its box is taller than it is wide).
- A line holding only a section number (`^\d+(\.\d+)*\.?$`) is merged with the following heading line when that line starts within two line heights of it, in any block.
- Levels: a size is a level only when at least `heading_level_min_count` (2) heading lines carry it, so one stray line in a larger size does not push the others down. Qualifying sizes rank by size, largest first, starting at 1. Every other heading follows them, at the depth of its number label (`1` is 1, `1.1` is 2), or at depth 1 without a label.

**Other units.**
- Captions begin with `Table` or `Figure` followed by a number. A caption joins the following lines of its block.
- A list item begins with a bullet glyph or an enumerator. A bullet-only line joins the next text line, in any block. A list item's `parent_id` is the nearest preceding `paragraph` or `heading` whose text ends with `:`, in the same section.
- A paragraph is a run of body lines of one column. Lines in different P1 blocks of the same column can continue a paragraph, because PyMuPDF often gives one-line blocks (474 of the 496 body blocks on pages 1 to 10 of the arXiv corpus document). A break occurs when the column changes, when the vertical gap exceeds `paragraph_gap_factor` (1.0) times the line height, when a line shorter than `short_line_fraction` of its column's widest line ends with terminal punctuation, or when a new list item or caption starts. A first-line indent also breaks a paragraph.
- Footnotes are body lines smaller than body size by `footnote_size_delta` pt, in the bottom `footnote_band_fraction` of the page. A footnote starts with a marker: a number, or one of `*` `∗` `†` `‡` `§` `¶`, followed by a space, a full stop or a parenthesis. A smaller line of the same column continues it.
- A body line that holds only digits or roman numerals, in the top or bottom `header_footer_band_fraction` band, is a page furniture unit (`header` or `footer`, `body_retrieval = false`).
- Lines inside a vertical or rotated box are not headings.

**Tables.** Cell geometry comes from pdfplumber `find_tables()` (lines strategy, as in P1).
- Preconditions: the page is not rotated, and the page box starts at the origin. When at least 3 text lines have their centre inside the table box, at least `table_min_claim_share` (0.5) of them must fall in cells. Otherwise the table is skipped and the page gets `table_geometry_mismatch` (warning). Its lines stay paragraphs.
- A P1 line belongs to a cell when its centre lies inside the cell box (1 pt tolerance). Lines outside every cell stay paragraphs.
- The first row is the header row. Its cells are `table_cell` units with `row_index` 0, and they supply `col_header` to the cells below.
- For each body row there is a `table_row` unit (`derived`), then one `table_cell` unit per non-empty cell, in column order. A cell's `parent_id` is its row unit. Its `row_header` is the text of the row's first cell, and its `col_header` is the header cell of its column.
- `table_id` is `{document_id}:p{page:04d}:t{n:02d}`, numbered per page from 1. The nearest caption on the same page, within 15% of the page height from the table box, is attached as `caption`.
- `table_header_uncertain` (warning) is raised when every header cell is numeric. Such cells become `warning`.
- A `TableCell` record mirrors ARCHITECTURE §6: `evidence_id`, `table_id`, `row_index`, `col_index`, `row_header`, `col_header`, `caption`.

**Invariants (tested).** For every document: each unit's spans reproduce its `raw_text`. A single-span unit is a verbatim slice of its page, and only table units have several spans. Every non-whitespace raw character of a structured page is covered by at least one non-derived unit. No two non-derived units share a raw character. Ordinals are contiguous per page. The `prev_id`/`next_id` chain is consistent. Section parents exist and have a lower level. A unit with a hidden line is never `verified`. The output is deterministic.

**Known limits (P2).**
- Reading order is P1's (D22). P1's column clustering can split a paragraph's short last line into another column. The corpus shows this in NIST SP 800-37r1 (page 20). P2 keeps P1's order and marks such pages `warning`, not `verified`.
- P1 does not detect running heads on the arXiv corpus document, so their text stays body text, and P2's furniture rule covers only page numbers.
- Heading detection is font-based. A heading set in the body's font without bold or a numbered label is not detected.
- Font sizes above body size are not always headings. On the arXiv corpus document, figure labels at 10 to 13 pt qualify as heading levels and push the section headings down to level 5 or 6. The rule is documented and uncalibrated (D26).
- Pdfplumber boxes that disagree with the text are skipped. On NIST SP 800-37r1, the RMF figure boxes on pages 81 to 85 (eight tables) are skipped for this reason, and their text stays paragraphs.
- Cover-page title lines in separate blocks become separate headings (NIST SP 800-37r1, page 1).

## 12. Storage, query and exact phrase contracts (P3)

Implemented in `app/storage` (schema, integrity checks, repository, `Store`) and `app/retrieval` (query building and the exact check). Errors: `StorageError`, `StorageIntegrityError` (a subclass) and `QueryError`, all in `app/common/errors.py`.

**Store.** `Store.open(path=":memory:")` runs `ensure_fts5_available()`, enables foreign keys, creates the schema on an empty database, and refuses a database whose `user_version` differs from the schema version. Its methods are `write_document(extracted, structure, *, created_at=None)`, `load_structure(document_id)`, `load_unit(document_id, evidence_id)`, `page_texts(document_id, pdf_pages)`, `document_ids()`, `has_document(document_id)`, `document_record(document_id)` and `match_units(document_id, fts_match)`. Every query takes a `document_id`, so no query crosses documents.

**Round trip.** `load_structure(document_id) == structure` for every structure written. The tests check it on synthetic fixtures and on the public corpus.

**Query building (`app/retrieval/query.py`).**
1. The phrase is normalized with `normalize_with_map` (§11). The query keeps the normalized text and the raw range of each of its characters, so a normalized character traces back to the raw phrase (`PhraseQuery.raw_range`).
2. A phrase that is not valid Unicode (a lone surrogate, for example), that contains a control character other than whitespace, or that has no letter or digit raises `QueryError`.
3. The MATCH expression is `index_text : "<normalized phrase>"`, with every double quote doubled. The whole phrase is one FTS5 string, so FTS5 tokenizes it with the index's tokenizer and the two sides cannot disagree about token boundaries. A per-token query did disagree: a private-use character, or a combining mark that unicode61 folds away, split the phrase where the index did not, and the phrase missed its own unit (`tests/unit/test_p3_tokenizer_agreement.py`). The column filter keeps heading text out of the candidate step. Inside the quotes, `AND`, `NEAR(…)`, `-`, `*`, `:`, `^`, parentheses and quotes are text, so `risk AND assessment`, `NEAR(a b)`, `-risk`, `risk*`, `a:b`, `^x` and `'); DROP TABLE …` are literal words, and the tests check it.

**Candidate step.** FTS5 is a superset filter. It ignores punctuation and spacing, folds case and folds diacritics, so it proposes units that the exact check then rejects. The FTS result is never returned on its own.

**Exact check (`app/retrieval/phrase.py`).** A unit matches when, for at least one of its spans, the normalized span text contains the normalized phrase under these rules:
- The text is the verbatim source (`pages.raw_text` through `source_spans`), never `index_text`, which carries generated glue in table units.
- The match lies inside one span, so it cannot cross the newline join of non-adjacent lines.
- Case is folded one character at a time, so the length is kept. A character whose lower case is more than one character is kept as it is (`'İ'.lower()` has two characters). A character is folded only where this build's FTS5 index folds it too (`index_foldable_characters`, calibrated once per process; D37). So the exact check never accepts a case pair that the candidate step cannot return.
- Diacritics are significant: `cafe` does not match `café`.
- Word boundaries: the character just before and just after the match must not be a letter, digit, underscore, combining mark or private-use character, whatever the phrase's own edge characters are. That set includes every character unicode61 keeps inside a token, so an exact match never ends inside an FTS5 token. So `3.5` does not match `13.5`, `3.55` or `x3.5`; `-5` does not match `3-5`; `U.S.` does not match `U.S.A`.
- Numbers: where the phrase starts or ends with a digit, a neighbouring `.` or `,` followed by a digit also rejects the match. So `3.5` does not match `3.5.2` or `1,3.5`, and `5` does not match `3.5`.
- Spacing and punctuation are significant: `3.5` does not match `3 5` or `3 . 5`; `risk assessment` does not match `risk. assessment`; `ABC 123` does not match `ABC-123`.

**Results.** `find_phrase(store, document_id, phrase) -> list[EvidenceUnit]`, ordered by `(pdf_page, ordinal)`. A unit with `derived = True` is a candidate only. Its spans point at real text, but its `index_text` is generated and must not be quoted (P6). Header and footer units are never returned.

**Known limits (P3).**
- No stemming, synonyms or ranking in the exact check. Ranking is P4 (§13), and the FTS5 index uses the default unicode61 tokenizer.
- CJK text without spaces forms long token runs. A phrase inside a run is not found (`文字` does not find `文字の認識`), but a phrase equal to a whole run is found. Substring retrieval for CJK needs another tokenizer, which V1 does not plan.
- Case folding means `US` also finds `us`. P5 and P6 decide entity and value matches. P3 only proposes candidates.
- A phrase copied from a table row's generated `index_text`, with its ` | ` or ` = ` glue, is not found. This is by design.
- BM25 statistics are per document (P4, D39, §13). The ranking index holds one document's body units, so a second document in the store does not change the scores of the first. Scores from different documents must not be compared.
- **A private-use character glued to a word hides the word.** `abcd` is one token for unicode61 and one word for the exact check, so `ab` and `cd` do not find it (pinned in `test_p3_phrase_check.py`). A symbol-font glyph with no space beside a word has this effect.
- **Derived table rows are found only through the text their generated index states.** P2 writes a row's `index_text` from the cells whose column has a header (§11), and it joins adjacent cells that share one raw line into one span (D28). So a value in a headerless column, or a phrase that crosses a cell boundary, does not find its row. The exact check accepts such a phrase where the span is verbatim, so the gap is a missed candidate, never a false acceptance. The recall test excludes exactly the windows that the row's index does not state: 16 of 481 on the public corpus, all derived rows.

The full corpus gives the size of the gap. 417 of 1,488 derived rows (28.0%) have at least one span that their index does not state, 571 spans in all. Each span falls into one of three groups:
- (a) 204 spans equal the text of one cell of the row. All 204 are found through their cell.
- (b) 330 spans are runs of whole cells, joined by P2's span merging. Each of the 735 constituent cells is found through its own unit. The cross-cell phrase returns the row in 0 of 330 cases, because the index does not state it.
- (c) 37 spans are parts of one cell's text (34, all found through that cell) or partial cross-cell merges (3, not classified further).

So every value is found through a cell unit, and what a derived row loses is only the cross-cell phrase. This is a P2 table-index limit, open as Q12 in `PROGRESS.md`.

- **Case folding follows the index, not Python alone.** On this build (SQLite 3.49.1) the index does not fold 416 of the 1,432 cased single characters in planes 0 and 1 (`index_foldable_characters`). They are mostly Cherokee, Old Hungarian, Georgian Mtavruli, Osage, Vithkuqi, Adlam, Warang Citi and Medefaidrin, with some Latin, Cyrillic, Greek and Glagolitic capitals. For those characters the phrase search is case-sensitive: `Ꭰ` does not find `ꭰ`, and that is a recall miss, never a false acceptance. The calibration follows the SQLite build, so an upgrade changes the set without a code change (`tests/unit/test_p3_case_folding.py`).
- **Recall evidence (P3, public corpus).** `tests/integration/test_p3_corpus.py` cuts whitespace windows from the normalized text of 174 sampled units across eight body content types, including every span of the sampled rows and cells. 465 windows were checked, and each found its own unit; 16 more were excluded as derived-row windows that the index does not state (above). That is recall for the windows the index states. It is not measured recall for the owner's document (B1, B3).

## 13. Retrieval contracts (P4)

Implemented in `app/retrieval` (`bm25.py`, `terms.py`, `rules.py`, `config.py`, `errors.py`) and in the store's read methods listed below. Configuration: `config/retrieval.toml` and `config/retrieval_rules.toml`. Errors: `QueryError` (the query is not text, or has no letter or digit), `StorageError` (no such document), and `RetrievalConfigError` with its subclass `RuleConfigError` (a configuration file is invalid).

**Entry point (D40).** `search(store, document_id, query, *, k=None, weights=None, context_window=None, expansion_k=None, rules=None, config=None) -> RetrievalResult`. An argument left at `None` takes its value from `config/retrieval.toml`. A parameter sweep passes its values as arguments, so it never edits the configuration file.

**Query words.** The query passes the P3 query validation and `normalize_with_map`. The normalized text is split at its single spaces. Each word is folded with `fold_case`, which follows the index, and duplicate words are removed. Each word becomes one quoted FTS5 string, with its double quotes doubled. The words are joined with `OR`. No stop-word list is used, because the IDF weight already lowers common words.

**Statistics are per document (D39).** `bm25()` runs on a temporary FTS5 table, `temp.document_bm25`. It has the same columns and tokenizer as `evidence_fts`, and it holds only the body units of the requested document. It is rebuilt on each search, which costs about 6 ms for 3,000 units on SQLite 3.49.1. The stored `evidence_fts` table is unchanged, and it remains the index for the exact-phrase candidate step (§12).

**Ranking.** `bm25(document_bm25, weight_index, weight_heading)`, sorted by the raw value ascending and then by `evidence_id`. A candidate's rank is its position in the result. The raw value is kept as `bm25_raw` for audit only. It is never a probability (SPEC §9).

**Expansion (one-way, recall only).** `expand_words` finds each rule's query terms as contiguous runs of folded query words. Each match adds the rule's alternatives. An alternative is quoted as an FTS5 phrase, so the words of a multi-word alternative must be adjacent. Every applied alternative is recorded in `trace.applied_rules` with the query term, the rule ID, the rule version and the alternative. The trace also holds the rule-set fingerprint, `trace.rules_fingerprint`, a SHA-256 of the canonical rule list. A unit that a rule reaches and no original query word reaches has `via = "expansion"` and `expansion_only = True`. Its `rule_ids` lists the rules whose alternatives reached it.

**Slots (D41).** The original-word hits come first. After duplicate removal, the first `k` of them are returned. Expansion-only hits follow, and at most `expansion_k` of them are returned. The trace counts what was cut, in `truncated_original` and `truncated_expansion`. An expansion never takes an original hit's place. A unit that an original word reaches always has `via = "original"`.

**Duplicates.** The key is the SHA-256 of `normalize_text(raw_text)`. Hits are read in rank order. The first hit with a key is kept. Each later hit with the same key is removed from the candidates and listed in the kept candidate's `duplicate_evidence_ids`. Removal happens before the `k` cut, and the removed copies are counted in `trace.duplicates_removed`. Nothing is dropped without a record.

**Context (D42).** A candidate's `context` holds:
- `before` and `after`: up to `context_window` body units before and after the candidate, in (`pdf_page`, `ordinal`) order. Header and footer units are skipped. Units in other sections and derived table rows are included.
- `section_heading_id` and `parent_heading_id`: the heading units of the candidate's section and of its parent section.

Context is never a candidate, never replaces one and is never quoted on its own. A separate list of all section siblings is not attached, because a whole section on every candidate would be too large. The in-section neighbours inside the window are the siblings.

**Carried flags.** Every candidate carries `derived` (a generated table row, which must never be quoted) and `extraction_quality` (`verified`, `warning` or `unverified`). Units from unverified pages are returned, not filtered, so that abstention can see them. P6 and P7 decide what they may support.

**Exact terms (D43).** `terms.extract_terms` finds numbers (`3.5`), percentages (`10%`), dates (`2024-01-01`, `4 March 2024`, `March 4, 2024`) and identifiers (`ABC-123`) in the query. Each candidate lists the query terms whose exact phrase is found in its raw text, using the P3 exact check (`exact_terms`). This is information for P6. It does not change the ranking. BM25 still matches `3.5` inside `3.5.2`, so a candidate without an exact term is a candidate, not a match.

**Store read methods (P4).** Each one takes a `document_id`, and each one scopes its SQL to it.
- `Store.document_bm25_index(document_id)`: a context manager that yields a `DocumentBm25Index`. It has `rank(fts_match, weights)`, which returns `(evidence_id, bm25_raw)` pairs in rank order, `indexed_ids()` and `row_count`.
- `Store.unit_summaries(document_id, evidence_ids)`: the rank-independent fields of each unit.
- `Store.body_neighbours(document_id, pdf_page, ordinal, window)`: the body units before and after a position.
- `Store.section_headings(document_id, section_id)`: the heading unit IDs of a section and of its parent.

**Configuration.** `config/retrieval.toml`, section `[retrieval]`: `k` (at least 1), `expansion_k` (at least 0), `weight_index` (above 0), `weight_heading` (above 0) and `context_window` (at least 0). Unknown keys are rejected. Every value is an uncalibrated default, and P9a sweeps them on the development split only.

`config/retrieval_rules.toml`: `rules_version = 1`, then zero or more `[[rule]]` tables. Each rule has `id` (lowercase, unique), `version` (an integer), `query_terms` (at least one), `alternatives` (at least one), `positive_examples` and `counter_examples` (each at least one `{query, text}` table) and `reviewer_note`. Stemming rules list the inflected forms explicitly; no stemmer runs. On loading, the P3 exact check verifies each rule against its own examples: every positive example's text must contain one of the alternatives, and no counter-example's text may contain one. A rule that fails its examples is rejected.

**Limits (P4).**
- Recall depends on the query words. A synonym that no rule lists is not found, and no rule is approved yet (D43).
- No stemming: `run` does not match `running` unless a rule lists it.
- BM25 candidates are a superset of exact matches (P3 limit): `3.5` also matches `3.5.2`.
- Stop words are not removed, so a long question returns many candidates, and `k` cuts them.
- Statistics are per document, so scores from two documents must not be compared.
- On a very small document, a term that occurs in more than half of its units has an IDF that FTS5 clamps to 1e-6, so many scores tie. The tiebreak is `evidence_id`.
- Recall is measured, not gated (D44). On the public corpus, 179 of 180 sampled windows return their own unit within K = 50, and 174 of 180 within K = 10. The one miss is a window of common words against a long unit, and it is recorded in `PROGRESS.md` (P4).

## 14. Question analysis and evidence selection contracts (P5)

Implemented in `app/question_processing` (`analysis.py`, `vocabulary.py`, `errors.py`) and `app/evidence` (`values.py`, `segment.py`, `markers.py`, `selection.py`, `errors.py`). Standard library and Pydantic only (`tests/unit/test_p0_dependencies.py`). No module makes a model call, a network call or a random choice. Errors: `QuestionError` (the question is not text, is blank, or has no letter or digit) and `SelectionError` (the inputs do not line up: a missing retrieval result, a result for a different query, or a missing unit).

**Question analysis (D52, D53).** `analyze(question: str) -> QuestionAnalysis`.
- `QuestionAnalysis`: `question` (as given), `components` (a tuple in question order, never empty), `compound` (true when there is more than one component).
- `QuestionComponent`: `component_id` (`c1`, `c2`, …), `text` (a verbatim slice of the question), `question_type` (`QuestionType`), `type_rule` (the rule that set the type, for example `type.how_many.v1`), `target_terms` (the subject words), `attribute_terms` (the requested-property words), `value_intent` (`ValueIntent`: `none`, `number`, `date_or_period`), `negated` (the question contains a negation word), `condition_terms` (condition words in the question), `reason` (why the component cannot be searched, or `None`), `flags`. The property `retrieval_query` is the target terms followed by the attribute terms, space-separated, without duplicates. It is the text the caller passes to `search()`.
- `QuestionType`: `what`, `who`, `when`, `where`, `how_many`, `which`, `whether`, `conditions`, `comparison`, `unsupported`.
- Compound questions are split at a question mark, and at `and`, `or` or `;` when the words after the separator open a new question (for example `who`, `when`, `is`, `does`). A later clause that uses a referential pronoun (`it`, `they`, `them`, `its`, `their`, `he`, `she`, `him`, `her`) takes the target terms of the clause before it (flag `target_inherited`). Its own words are predicates and do not replace that subject. If the clause before it has no target terms, the later clause is ambiguous (flag `pronoun_without_subject`). A pronoun in a single question, as in `is it permitted`, is not treated this way (D56). A comparison is split into one component per subject only when the subjects are explicit (`between A and B`, `A versus B`, `compare A with B`). Otherwise the component is `ambiguous` (flag `subjects_unclear`).
- Unsupported: a question that opens with no recognised question word, `why` questions, and `how` questions that are not about a quantity (for example `how is the fee calculated`). The component has `reason` set and is never searched.
- Ambiguous: a component with no target terms (for example `what is the maximum amount?`). The reason is recorded and the component is never searched.
- Target terms are the content words that are not function words, question words or attribute words. Attribute words come from a controlled list (for example `amount`, `limit`, `period`, `fee`, `days`), together with light predicate verbs (`apply`, `need`, `require`, `include`, `happen`, and similar). Neither kind is required in the sentence (D53). No stemming and no synonyms are applied (D38, D58).

**Evidence values (D51).** `find_values(text, *, count_nouns=()) -> tuple[Value, ...]`. `Value` has `kind` (`number`, `percent`, `currency`, `date` or `period`), `text` (verbatim), `start` and `end` (half-open offsets in `text`), `unit` (lower-case label or `None`), `range` (a numeric or year range) and `negative`. `count_nouns` are the target words of the question. A number counts through one of them only when the noun is lower case as written, the number is not dotted, and the number does not open a line (D59). A number directly after a label word (`Section`, `Table`, `Step`, `Page`, and similar) is not a value at all (D59).
- Not values: a token with more than one separator (`3.5.2`, `1,2,3`), a hyphen-glued identifier (`ABC-123`, `800-53`), and a footnote mark glued after a letter or punctuation (`FISMA,1`, `agencies.2`). A number followed by a unit may be separated by spaces or line breaks (`30 \n\ndays`). The quote stays the raw slice. A hyphenated unit is read (`30-day`).

**Sentences (D50).** `sentence_spans(text) -> tuple[tuple[int, int], ...]`, half-open offsets into `text`. A sentence ends at `.`, `?` or `!` followed by whitespace and a capital letter, a digit or an opening quote. Line breaks are whitespace, so a line wrap never ends a sentence. A full stop after an abbreviation (`e.g.`, `i.e.`, `vs.`, `No.`, `Dr.`, `U.S.`, initials, `et al.`) does not end a sentence unless the next word is a sentence-opening word (`The`, `This`, `It`, …). A full stop before a lower-case letter never ends a sentence.

**Markers.** `find_markers(text, kind)` for `permission` (with a `negative` flag, for example `must not`, `is not permitted`, `prohibited`, `is required`), `condition` (`if`, `unless`, `provided that`, `except`, `subject to`, `only if`, `when`, `where`) and `list` (`including`, `such as`, `the following`). Longer phrases win over their parts, and matches do not overlap.

**Selection (D45–D49, D54).** `select_candidates(analysis, retrieved, units) -> SelectionResult`.
- `retrieved`: a mapping from `component_id` to the `RetrievalResult` of `search(store, document_id, component.retrieval_query)`. A searchable component without an entry, or a result whose `query` differs from `retrieval_query`, raises `SelectionError`.
- `units`: a mapping from `evidence_id` to the `EvidenceUnit` for every candidate the retrieval returned (loaded with `Store.load_unit`). A missing unit raises `SelectionError`.
- `SelectionResult`: `question` and `components`, one `ComponentSelection` per analysis component, in order. A component is never omitted, even when it has no candidates.
- `ComponentSelection`: `component_id`, `question_type`, `status` (`ComponentStatus`: `candidates`, `expansion_only`, `no_candidates`, `unsupported`, `ambiguous`), `reasons` (a tuple of plain-text reasons, for example `no retrieved sentence contains every target term`), `candidates` (in retrieval rank order) and `dropped`.
- `status` is `candidates` when at least one candidate was reached by an original query word, and `expansion_only` when only reviewed rules reached them (D38: never support). `candidates` does not mean the question is answered. Verification (P6) and the decision (P7) decide that.
- `AnswerCandidate`: `component_id`, `question_type`, `retrieval` (the P4 `RetrievalCandidate`, kept by reference, so its scores, `via`, `rule_ids`, `duplicate_evidence_ids` and context stay with retrieval), `pdf_page` and `section_id` (the citation, SPEC §6, taken from the unit, D57), `rule_id`, `granularity` (`sentence` or `passage`), `quote` (verbatim), `page_start` and `page_end` (half-open offsets into the page's raw text, so `page_text[page_start:page_end] == quote`), `answer_span`, `answer_page_start`, `answer_page_end` and `answer_kind` (all `None` when no rule gives an answer span), `values` (the values in the quote, with offsets relative to the quote), `negated` (for a permission marker), `attribute_hits` (the question's attribute words found in the quote) and `flags`.
- `DroppedCandidate`: `evidence_id` and `reason`. Only two reasons exist: `derived_row` (a generated table row is never quoted, D28) and `crosses_source_span` (a quote would join two source spans, so it is not verbatim). Nothing is dropped silently.

**Rules (version 1).** Each candidate records the rule that produced it.

| Rule | Question type | Quote granularity | Answer span |
| --- | --- | --- | --- |
| `what.sentence.v1` | what | sentence containing every target term | none (`no_answer_span`) |
| `who.sentence.v1` | who | sentence | none (`no_answer_span`) |
| `where.sentence.v1` | where | sentence | none (`no_answer_span`) |
| `which.sentence.v1` | which | sentence (flag `list_marker` when a list marker is present) | none (`no_answer_span`) |
| `when.date_or_period.v1` | when | sentence with a date or period | the date or period, when exactly one is present (otherwise `multiple_values`) |
| `how_many.value_with_unit.v1` | how many | sentence with a number and a unit, a percentage, a currency amount, or a number with a count noun from the question | that value, when exactly one is present (otherwise `multiple_values`) |
| `whether.permission_marker.v1` | whether | sentence with a permission or prohibition marker | the marker, when exactly one distinct marker is present (otherwise `multiple_markers`); `negated` from its polarity |
| `conditions.passage.v1` | conditions | the whole passage (the unit) with a condition marker and every target term | none (`no_answer_span`) |
| `comparison.subject_sentence.v1` | comparison | sentence containing the subject's target terms (flag `comparison_subject`) | none (`no_answer_span`) |

- Table cells (`table_cell`) are passage-only: the quote is the whole cell, the flag `table_cell` is set, and no answer span is given, even for a value (D48).
- Derived table rows (`table_row`, `derived = True`) are never quoted. Each one is listed in `dropped` with reason `derived_row` (D48, the P4 handoff rule, until Q12 is settled).
- A quote that crosses a join between source spans is never built, because it would not be verbatim. Its unit is listed in `dropped` with reason `crosses_source_span` (D49).
- A quote containing U+FFFD (the replacement character, as in `nation�s`) is kept and flagged `replacement_character`. It is not dropped, because P6 decides what it may support.
- `ComponentSelection.status` is `ambiguous` or `unsupported` for those components, and no retrieval result is required for them.
- Determinism: the same question, the same retrieval results and the same units give the same `SelectionResult`, including order.

**Limits (P5).**
- The rules cover the nine supported question types. Name and place extraction is not attempted (D47), so `who` and `where` answers are passages only.
- Written numbers (`three days`) are not values. A passage with only a written number cannot give a `how_many` answer span.
- Only the candidates that retrieval returned are examined, so the retrieval depth `k` limits recall.
- A target term must appear in the same sentence as the value or marker. An answer split across two sentences is not found.
- The abbreviation list and the marker lists are uncalibrated heuristics. They are reviewed on the public corpus, and the counts of how often each rule fires are recorded in `PROGRESS.md` (P5). Nothing is tuned to a gold answer.

## 15. Evidence verification contracts (P6)

Implemented in `app/verification` (`errors.py`, `vocabulary.py`, `report.py`, `terms.py`, `checks.py`, `verifier.py`). Standard library only. The store reads are `Store.load_unit`, `Store.page_texts` and `Store.page_warning_codes`. The last one is added in P6: it reads the `pages.warnings_json` column that P1 and P3 already write, and the schema does not change. No model call, no network call and no random choice.

**Entry point (D61).** `verify(candidate, analysis, store, document_id) -> VerificationReport`. `candidate` is a P5 `AnswerCandidate`, and `analysis` is the `QuestionAnalysis` it was selected for. `VerificationError` is raised only when the inputs do not line up: the component is missing, its question type differs from the candidate's, or the component is not searchable.

**The candidate is a claim (D61).** Each check re-reads the stored page text and the stored unit, and recomputes what it needs: values with P5's parser `find_values`, the permission marker and its polarity with `find_markers`, the target and property words with P3's exact check `span_matches`, and the neighbours through `prev_id` and `next_id`. The candidate's `values`, `attribute_hits` and `negated` are never copied. A mismatch is FAIL, not a silent correction.

**Checks.** Every check returns a status (`PASS`, `FAIL`, `UNRESOLVED` or `NOT_APPLICABLE`) with a reason, and a rule ID `verify.<name>.v1`.

| Check (SPEC §7) | Name | PASS when | FAIL when | UNRESOLVED when | NOT_APPLICABLE when |
| --- | --- | --- | --- | --- | --- |
| 1 Quotation integrity | `quotation` | the quote equals the stored page text at `page_start:page_end` | the quote is empty, the page has no stored text, the offsets are out of range, or the text differs | never | never |
| 2 Location integrity | `location` | the unit exists and lies on the candidate's page and section; it is body text and not derived; its quality and rule agree with the candidate; the quote lies inside one source span | any of these fails | never | never |
| 3 Answer-span integrity | `answer_span` | (answer types) the span lies inside the quote and equals the stored text at its offsets; the value read from the quote is the only one of the required kind and matches the claimed span and kind (polarity is checked by the negation check) | (answer types) any of these fails; (passage types) any span is present | (answer types) no span, with the P5 flag as the reason; (passage types) always, because no rule gives a span (SPEC §6) | never |
| 4 Entity consistency | `entity` | every target word of the question occurs in the quote (`span_matches`) | a target word is absent, or the candidate is expansion-only (D38) | the question has no target word | never |
| 5 Attribute consistency | `attribute` | at least one property word of the question occurs in the quote | never | no property word occurs (synonyms are not used) | the question has no property word |
| 6 Value integrity | `value` | every number, date or identifier of the question occurs in the quote (D63), and not only with a minus sign | a question value occurs only with a minus sign, or the candidate is expansion-only (D38) | a question value does not occur | the question has no number, date or identifier |
| 7 Context validation | `context` | the page is `verified`, and neither immediate neighbour (`prev_id`, `next_id`) holds a strong qualifier (D62) | never | the page is not `verified` (D62), a neighbour holds a strong qualifier, or a neighbour cannot be loaded | never |
| 8 Negation validation | `negation` | (whether) exactly one permission marker, its polarity equal to the candidate's `negated`, the question not negated, and no negation or hedge word outside the marker; (other types) no negation or hedge word in the quote | the stored polarity differs from the passage's, or the candidate is expansion-only (D38) | the question is negated, the passage does not have exactly one marker, or a negation or hedge word is present | never |
| 9 Condition validation | `condition` | no condition marker and no strong qualifier in the quote | the candidate is expansion-only (D38) | a condition marker or a strong qualifier is in the quote | never |
| 10 Conflict screening | `conflict` | not evaluated here | not evaluated here | not evaluated here | always: pending in the decision step (D66). It is listed in `pending` and is not part of the verdict |
| 11 Source quality | `source_quality` | the stored page status is `verified` | never | `warning` or `unverified`, with the page's issue codes as the reason (D62) | never |
| P5 flags (D64) | `candidate_flags` | the candidate has no P5 flag | never | at least one P5 flag, or an unknown one | never |

**Required checks per type (D65).** Every type requires the same ordered list: `quotation`, `location`, `answer_span`, `entity`, `attribute`, `value`, `context`, `negation`, `condition`, `source_quality`, `candidate_flags`. Conflict screening is pending (D66). The types differ only in the answer-span rule.

| Type | Answer span from P5 | Can PASS |
| --- | --- | --- |
| `when`, `how_many`, `whether` | one value or marker, when a rule gives exactly one | yes, when every required check passes |
| `what`, `who`, `where`, `which`, `conditions`, `comparison` | none (passage only) | never: `answer_span` is UNRESOLVED, so the verdict cannot be PASS |

**Verdict (D61).** FAIL when any required check is FAIL. PASS when every required check is PASS, where NOT_APPLICABLE is allowed only for `attribute` and `value`. UNRESOLVED otherwise. A PASS is a candidate-level verdict. It is not a final answer, because the decision step (P7) still runs conflict screening and the acceptance policy.

**Pages that are not verified (D62).** `source_quality` passes only on a `verified` page. A `warning` or `unverified` page gives UNRESOLVED, and the reason lists the page's stored issue codes. The stored record does not say which warning applies to a page, so every page that is not verified counts as order-uncertain for `context` (Q11, option b, applied conservatively). If reading order is repaired first (Q11, option a), more pages become `verified` and can pass. The answer to Q11 changes how many pages count as clean. The code is the same either way.

**Vocabulary v1 (D62).** Matching is case-insensitive and uses word boundaries.
- Strong qualifiers: `except`, `unless`, `only if`, `provided that`, `does not apply`, `do not apply`, `however`, `subject to`.
- Condition markers: the P5 list (`find_markers(text, "condition")`).
- Negation words: `not`, `no`, `never`, `none`, `nor`, `neither`, `cannot`, `without`, `nothing`, and the contraction `n't`.
- Hedges: `might`, `could`, `possibly`, `probably`, `perhaps`, `unclear`, `uncertain`, `appears to`, `seems to`, `is likely`, `are likely`.

**Value occurrence (D63).** A question value (P4's `extract_terms`: numbers, percentages, dates and identifiers) occurs in a passage when the passage, normalized with the index rules, has it with these boundaries. The character before is not a letter, digit, underscore, `.`, `,` or `/`. The character after is not a letter, digit or underscore, and not a `.`, `,` or `/` followed by a letter or digit. A space in the term matches any whitespace. An occurrence is negative when a minus sign (`-`, U+2212 or `–`) comes before it and the character before that sign is not a letter, digit or `)`. So `10-15` is positive, while `-3.5` and `(-3.5)` are negative. These boundaries are stricter than P3's phrase check, which does not read the sign and does not split `3.5` from `3.5.2`. Tests pin `3.5` against `-3.5`, `3.5.2`, `1,2,3`, `5` inside `15`, and `13.5`.

**Blocking P5 flags (D64).** `no_answer_span`, `multiple_values`, `multiple_markers`, `table_cell`, `list_marker`, `comparison_subject` and `replacement_character` each give UNRESOLVED on `candidate_flags`. An unknown flag does too. A derived table row is never quoted (D28), so `location` FAILs on one.

**Expansion-only (D38).** A candidate whose `expansion_only` is true FAILs `entity`, `value`, `negation` and `condition`. Its other checks run as usual.

**Output (auditable).** `VerificationReport` holds `verifier_version` (`verify.v1`), `document_id`, `evidence_id`, `component_id`, `question_type`, `verdict`, `checks` (in the table order, each with `name`, `rule_id`, `status` and `reason`), `pending` (`conflict`), and `reasons` (the reasons of every check that is neither PASS nor NOT_APPLICABLE).

**Limits (P6).**
- Rules can show that a passage has the question's words, values, markers and polarity. They cannot show that the passage answers the question (SPEC §7).
- The negation check reads the sentence only. The context check reads the two neighbours for strong qualifiers only, not for negation words.
- The neighbours are `prev_id` and `next_id`, not the retrieval window, so the result does not depend on `context_window`.
- The vocabulary is reviewed by reading. It is not calibrated on any gold answer.

## 16. Conflict screening and decision contracts (P7)

Implemented in `app/conflict` (`config.py`, `claims.py`, `detector.py`) and `app/decision` (`errors.py`, `policy.py`, `response.py`, `engine.py`). Configuration: `config/conflict.toml` (measure families and supersession phrases) and `config/acceptance_policy.toml` (gates). The store gains one read, `Store.page_extraction_method`, which reads `pages.extraction_method`. No schema change. No model, no network call, no random choice, no timestamp in the response.

**Entry point (D68).** `answer(store, document_id, question, policy=None, *, retrieval_config=None, rules=None, conflict_config=None) -> QAResponse`. It raises `QuestionError` for an empty question, `StorageError` for an unknown document, `PolicyError` and `ConflictConfigError` for a bad configuration file. "No answer" is never an exception: it is a status.

**Pipeline per call.** `analyze` (P5) → for each searchable component: `search` (P4), `load_unit`, `select_candidates` (P5) → `verify` each candidate (P6) → screen the component (§16.2) → decide the component (§16.4) → aggregate (§16.5) → build and validate the response (§16.7).

**16.1 Acceptance (D69).** `accepts(report, policy)` is the only place where a candidate is accepted. A candidate is accepted when every required check is PASS, or NOT_APPLICABLE on `attribute` or `value`, or UNRESOLVED on a relaxable check whose gate is off. Relaxable checks: `attribute`, `value`, `entity`, `context`, `negation` and `condition`. Never relaxable, and not in the policy file at all: `quotation`, `location`, `answer_span`, `source_quality`, `candidate_flags`. FAIL is never accepted. The default policy has every gate on, so `accepts` equals the verdict PASS (a test pins this, and each gate has one synthetic case that it changes).

**16.2 Screen (D70; document-wide, independent of retrieval depth).** For a component of an answer type (when, how_many, whether) the screen takes every unit that contains each target term. It uses P3's exact check `find_phrase` once per target term and intersects the results by evidence ID, in `(pdf_page, ordinal)` order. Inside each unit, a piece is a sentence (a table cell or a conditions passage is one piece, as in P5) that contains every target term under `span_matches`. A derived table row is screened on its raw text. It cannot be CONFIRMED (§16.3). A component with no target term is not screened, so its candidates cannot pass the entity check (P6).

Claims of a piece, by question type:
- `when`: its DATE and PERIOD values. Family `date` or `period`. Key: the normalized text (case folded, whitespace collapsed).
- `how_many`: quantities (percent, currency, or a number with a unit) and bare numbers (no unit, not a range). A quantity's family comes from `config/conflict.toml`; a unit that is not listed forms its own family. Key: number and unit label, both normalized. A bare number has family `bare` and key: its number.
- `whether`: the polarity of each permission marker. Family `polarity`.
- Other types: no claims, and no screen.

For `how_many` and `whether`, the DATE and PERIOD values of a piece are its effective dates, not claims.

Comparing two claims: a bare number is compared with any quantity by its number. Two claims with units are comparable only in the same family (no unit conversion; `30 days` and `1 month` differ). A date is comparable with a date only. Polarity is comparable with polarity. Two claims that are not comparable give no relation.

**16.3 Relations (D71).** For each pair of pieces, and each pair of comparable claims that differ, the first rule that holds gives the relation:
1. `EXPLICIT_SUPERSESSION`: a configured phrase (whole words, case-insensitive; `config/conflict.toml`) is in either piece.
2. `DATED_CHANGE`: both pieces have effective dates and the sets differ.
3. `DIFFERENT_SCOPE`: the scope words of the two pieces differ. Scope words are the words of the piece that are not target words, value words, function, question, attribute, negation or pronoun words, marker words, or tokens with a digit.
4. `CONFIRMED_INCOMPATIBLE`: the scope words are equal, the effective dates are equal (both empty, or the same set), and neither piece is a derived row.
5. `POTENTIAL_DISCREPANCY`: any other case (one piece is dated and the other is not, or a derived row is involved).

Equal claims give no relation and are counted as agreeing pairs. A piece is never compared with itself. Its claims are compared with the claims of every other piece, including another piece of the same unit. So a sentence that states 30 days and 45 days blocks an answer whenever another passage gives a differing value. Such a sentence cannot be the answer itself: P5 flags it (several values), and P6 does not accept a flagged candidate.

**Impact (D71).** `CONFIRMED_INCOMPATIBLE` and `EXPLICIT_SUPERSESSION` give the impact CONFLICT when both pieces are clean (verified source and not a derived row). Otherwise they give SOURCE. `DATED_CHANGE`, `DIFFERENT_SCOPE` and `POTENTIAL_DISCREPANCY` give AMBIGUOUS. Scope words choose only which label is shown. They never permit an answer, because ANSWERED needs the absence of every non-equal relation in the component. Supersession never grants an answer in V1: naming the superseding value needs a direction parser, which V1 does not have. The statement is shown and the answer abstains (SPEC §8, "only apply precedence when the document establishes it").

**16.4 Component status (D72).** The first rule that holds gives the status:
1. Not searchable: AMBIGUOUS_QUERY (`unsupported_question` or `ambiguous_question`).
2. Any CONFLICT impact: CONFLICT (`conflict_confirmed` or `conflict_supersession`).
3. Any SOURCE impact: SOURCE_UNVERIFIED (`source_quality`, with the discrepancy in the reasons).
4. An accepted candidate exists: AMBIGUOUS_QUERY if any AMBIGUOUS impact (`scope_differs`, `date_differs` or `potential_discrepancy`); otherwise ANSWERED (`answer_verified`, and `relaxed_gate_used` when an accepted candidate has an open check that a relaxed gate let through).
5. No accepted candidate: SOURCE_UNVERIFIED if some candidate's non-PASS checks are only `source_quality` and `context` (both come from the page's quality, D62). Otherwise AMBIGUOUS_QUERY if any AMBIGUOUS impact. Otherwise INSUFFICIENT_EVIDENCE with `no_candidates`, `expansion_only`, `no_verified_answer` (passage-only types, §16.6) or `verification_failed` / `verification_unresolved`.

Rule 5's source test uses the verifier's check statuses, not the text of the reasons.

**16.5 Overall status (D72).** ANSWERED when every component is ANSWERED. PARTIAL when at least one component is ANSWERED and at least one is not (the response still lists each component's own status). Otherwise the first of CONFLICT, SOURCE_UNVERIFIED, AMBIGUOUS_QUERY and INSUFFICIENT_EVIDENCE that any component has. A single-component question is never PARTIAL.

**16.6 Passage-only types (D73).** `what`, `who`, `where`, `which`, `conditions` and `comparison` are never ANSWERED (D65). Their candidates are returned as evidence for inspection, with `no_verified_answer`, and the status is INSUFFICIENT_EVIDENCE. The six SPEC §9 statuses are the only ones, so no seventh status is added. This choice is recorded for the owner to confirm.

**16.7 Response model (D74).** `QAResponse` is a frozen Pydantic model that forbids extra fields. Its sections are kept apart (SPEC §10): `status`, `question`, `answer_spans`, `evidence`, `warnings`, `reason_codes`, then `components`, `retrieval`, `verification`, `conflicts`, `screening`, `policy` and `engine_version`. Validated invariants (tests pin each one):
- answer spans appear only when the status is ANSWERED or PARTIAL;
- ANSWERED means every component is ANSWERED; PARTIAL means a mix of answered and not answered components;
- every answer span names an evidence item of the response, and its text equals the item's quote at the span's page offsets;
- every quoted evidence item has `source_end - source_start == len(quote)`;
- BM25 appears only as a raw rank with its score labelled raw and uncalibrated, never as a probability (SPEC §9).

**16.8 Determinism (D74).** The same PDF bytes, question, retrieval configuration, conflict configuration and policy give equal responses. Order: components in question order; evidence by `(pdf_page, ordinal)`; relations in piece order, then claim order. The test compares two independent runs.

**16.9 Limits (P7).**
- The screen covers passages that contain every target word exactly (D58). A passage that states the same fact with other words is not screened. A passage with the subject words and no value is not a claim.
- A bare number is compared with the answer by its number. A sentence with an unrelated bare number (for example `after 2 approvals`) can therefore block an answer. This is the safe direction, and it costs recall.
- Supersession never grants an answer (above). Passage-only types never pass (D65).
- The scope and date tests are heuristics, reviewed by reading. They choose labels, and every case without an answer is an abstention. None is calibrated on gold data (B1, B3).
- A PASS is still candidate-level evidence. The answer is the decision's output, and it has been checked only on synthetic documents, because the public corpus has no PASS on a verified page (P6, D62).

## 17. Evaluation contracts (P8a)

Implemented in `app/evaluation` (`errors.py`, `text.py`, `gold.py`, `scoring.py`, `metrics.py`, `runner.py`). The store gains two methods, `Store.record_evaluation` and `Store.read_evaluation`, which use the existing `evaluations` table. No schema change (`SCHEMA_VERSION` stays). The regression framework is `tests/fixtures/regression_cases.py`, `tests/regression/test_p8_known_failures.py` and `tests/regression/known_failures.jsonl`. Synthetic gold lives in `tests/fixtures/`, never in `data/evaluations/gold/`. The harness reads responses from `answer()` and never changes the store.

**17.1 Text rule (D76).** Quotes, answer texts and containment tests compare `normalize(s) = " ".join(s.split())`. Any run of whitespace, including a line break from a line join, is one space. Case, punctuation, diacritics and every other character are compared exactly. There is no case folding, no stemming and no fuzzy matching.

**17.2 Gold record (D75).** A `.jsonl` file, read through `app/common/files.py`, with one JSON object per line. Extra fields are refused.

| Field | Type and rule |
| --- | --- |
| `record_id` | `^[a-z0-9][a-z0-9-]{0,62}$`, unique in the file |
| `question` | text, not blank after trimming |
| `category` | one of the SPEC §11 categories: `direct_fact`, `numeric_date`, `table`, `paraphrase`, `negation_exception`, `multi_passage`, `compound`, `unanswerable`, `ambiguous`, `conflicting`, `ocr_extraction_edge` |
| `source` | `synthetic` or `owner_document` |
| `split` | `dev` or `heldout` |
| `annotator` | text, not blank |
| `expected_status` | one of the six SPEC §9 statuses |
| `evidence` | list of `{component >= 1, pdf_page >= 1, quote (not blank)}` |
| `answers` | list of `{component >= 1, text (not blank)}` |

A record is **answerable** when `expected_status` is `ANSWERED` or `PARTIAL`. Otherwise it is **unanswerable**. A component index is **expected answerable** when the record is answerable and the record has gold evidence for that index.

**Passage-only types (D88).** A question of a type that the system never answers by design (`what`, `who`, `where`, `which`, `conditions`, `comparison`) is labelled answerable when the document answers it. Its gold record has evidence and no answer spans, because these types return passages and not spans. The harness scores the design abstention as an incorrect abstention, and §17.10 shows it by question type.

**17.3 Validation, layer 1: the file alone (D77).** `GoldRecord` refuses: an answer on an unanswerable record; an answerable record with no evidence; an answer whose normalized text does not occur in a normalized evidence quote of the same component; a duplicate `record_id`; a line that is not valid JSON (the error names the line); an empty file.

**17.4 Validation, layer 2: the stored document (D76, D77).** `check_against_store(record, store, document_id)` refuses: a page that is not in the document; a quote that does not occur verbatim (17.1) in the stored raw text of its page; a component index above the number of components that `analyze(question)` returns; for `ANSWERED`, a component with no gold evidence; for `PARTIAL`, no component with gold evidence, or no component without it. It raises `GoldError`, naming the record and the reason. Inexact quotations are refused here, not in layer 1. The check runs for every selected record before the first `answer()` call.

**17.5 Split and source guard (D84).** `load_gold(path)` returns `GoldDataset` with the records, the SHA-256 of the file's bytes and the file name. `select_split(dataset, split, *, final_run)` runs before any `answer()` call:
- `split` must be `dev` or `heldout`. Any other value, including "all", is refused.
- `heldout` requires `final_run=True`. `dev` with `final_run=True` is refused.
- The result holds only records of that split. A run that mixes `source` values is refused.

The guard is a function parameter, not a command-line flag. The command-line interface arrives in P10.

**17.6 Outcomes (D78).** Components are numbered from 1 in question order. For component i of a response:
- `accepted_i` is true when the component's status is `ANSWERED`.
- `correct_i` is defined only when `accepted_i` holds. It is true when component i is expected answerable and the answer matches the gold:
  - if gold answers exist for i, some answer span of component i has a text equal to a gold answer of i, and the evidence item that carries that span contains a gold quote of i;
  - otherwise some evidence item of component i contains a gold quote of i.

Each record receives one outcome:

| Outcome | Condition |
| --- | --- |
| `correct_answer` | answerable; at least one accepted component; every accepted component correct; every expected-answerable component accepted |
| `incomplete_answer` | answerable; at least one accepted component; every accepted component correct; some expected-answerable component not accepted |
| `incorrect_answer` | answerable; at least one accepted component is not correct (an accepted component that was not expected also counts) |
| `incorrect_abstention` | answerable; no accepted component |
| `correct_abstention` | unanswerable; no accepted component |
| `false_acceptance` | unanswerable; at least one accepted component |

A `PARTIAL` response is judged one component at a time. A wrong accepted component makes the record `incorrect_answer`, even when another component is right.

**17.7 Retrieval measures (D80).** Measured for each component that has gold evidence.
- The cut `k_cut` is the `k` of that component's retrieval summary. A component that was not searched has an empty list, and its cut is the configured `k`.
- A returned unit is a **hit** for gold quote g when the unit lies on g's page and `normalize(g)` occurs in `normalize(unit.raw_text)`. A unit is **credited** for the first hit of a gold quote that no earlier unit has credited.
- Recall@K = gold quotes whose first hit has rank at most K, divided by the number of gold quotes G.
- Precision@K = hits among ranks 1 to K, divided by K. The denominator is K even when fewer units were returned.
- nDCG@K = (sum over credited units with rank at most K of 1/log2(rank+1)) divided by (sum for j = 1 to min(K, G) of 1/log2(j+1)). Binary gain.
- MRR = 1 divided by the rank of the first hit in the returned list, or 0 when there is none.
- A metric at K is defined only when K is at most `k_cut`. Otherwise it is `None`. Recall is never reported at a depth the engine did not search.

**17.8 Answer and evidence measures (D81).**
- Exact match: over gold answers, the share with a span of the same component whose normalized text equals the gold text.
- Token F1: over gold answers, the best F1 over the spans of the same component, on `\w+` tokens of the normalized texts. 0 when there is no span.
- Status accuracy: the share of records whose status equals `expected_status`.
- Quotation accuracy: over evidence items that have a quote, the share where `page_text[source_start:source_end] == quote` exactly. The page text is read from the store. Items without a quote are counted apart, not scored.
- Answer-span integrity: over answer spans, the share where `page_text[start:end] == text` exactly.
- Citation page accuracy: over accepted, expected-answerable components, the share with an evidence item on a gold page of that component.
- Evidence support: over accepted, expected-answerable components, the share with an evidence item that contains a gold quote of that component.
- Unsupported answer rate: over accepted components, the share with no evidence item that carries an accepted verification (`CandidateVerification.accepted`) for the same component.

**17.9 Rates and empty denominators (D79).** A rate is successes divided by n. When n is 0 the rate is `None`, never 0.0, and n is still reported. Every rate reports n and a Wilson 95% interval, with z = 1.959963984540054. A mean over records follows the same rule.

Question-level rates, where "total" is every selected record:
- coverage = accepted / total;
- correct answer rate = `correct_answer` / answerable;
- incomplete answer rate = `incomplete_answer` / answerable;
- incorrect abstention rate = `incorrect_abstention` / answerable;
- correct abstention rate = `correct_abstention` / unanswerable;
- false acceptance rate = `false_acceptance` / unanswerable;
- incorrect accepted answer rate = (`incorrect_answer` + `false_acceptance`) / total;
- selective risk = (`incorrect_answer` + `false_acceptance`) / accepted.

Component-level counts and rates: accepted components, incorrect accepted components, expected-answerable components not accepted, with their rates over the matching denominators.

**17.10 Breakdowns (D82).** Every count and rate of 17.9 is also reported for each category (the gold `category`) and for each question type. A record's question type is the type of its only component, or `compound` when it has several. Each group is its own table. No group is merged into another.

**17.11 Risk-coverage ordering (D83).** The points are the accepted records, ordered by the best rank that their accepted components' evidence has in its retrieval list (rank 1 is best), then by `record_id`. Point j has coverage = j / total and risk = errors among the first j, divided by j. An error is `incorrect_answer` or `false_acceptance`. This orders the engine's own output. It is not a probability (SPEC §9). With tied ranks the curve is flat or degenerate, and it is reported as it is.

**17.12 Run record (D85).** `run_evaluation(store, document_id, dataset, split, *, final_run=False, output_dir, run_id=None, created_at=None, policy=None, retrieval_config=None, rules=None, conflict_config=None)`.
- `<output_dir>/<run_id>.json` holds the run: `run_id`, `created_at`, `engine_version`, `split`, `final_run`, `source`, a synthetic banner when the source is synthetic, the dataset (`sha256`, `record_count`, file name), the configuration (policy version and SHA-256, calibration flag, retrieval `k`, `expansion_k`, `context_window`, the rule-set fingerprint, the cut depths, the confidence level), the metrics, the risk-coverage points, one entry per record, and the limitations.
- The `evaluations` row holds `run_id`, `created_at`, `split`, `dataset_sha256`, `config_json` (the configuration) and `metrics_json` (counts, rates, breakdowns and risk-coverage points). Both JSON texts use sorted keys. `metrics_json` holds no id, no timestamp and no per-record list, so the same inputs give the same text. A test compares two runs with different ids and times.
- `run_id` is 1 to 80 letters, digits, dots, dashes or underscores, starting with a letter or digit, because it names the file. Any other value is refused before anything is written.
- `output_dir` is a required argument. Tests write to `tmp_path`. `data/evaluations/runs/` is written only by the command-line interface, in P10.

**17.13 Regression framework (D86).** `tests/regression/known_failures.jsonl` lists open known failures, one JSON object per line. The file starts empty. Each entry has: `id` (kebab-case, unique); `phase`; `summary`; `question`; `expected_status`; `document`, which is either `{"items": [{"page", "text", "content_type"}, ...]}` inline or `{"fixture": "<registered id>"}`; and `reason`. The registered ids are in `tests/fixtures/regression_cases.py`. The rules:
- every entry is validated (schema, unique `id`, a known fixture id);
- an open entry must still fail. If the engine now gives the expected status, the test fails and names the entry, so the entry moves to a regression module next to its fix;
- a deliberately regressing case must be reported. A test writes one to a temporary file and checks that the mechanism reports it.

Each discovered false answer still gets its own regression module (SPEC §12).

**17.14 Scope limits (P8a).**
- The harness is checked only on synthetic gold, labelled `source: synthetic`. Its results describe the test set, not the owner's document. DoD item 9 stays blocked on B3.
- The extraction measures of SPEC §11 (page extraction success, reading-order failures, table-structure accuracy, OCR error review) are not computed in P8a. Their meaning depends on the owner's document, so they belong with the real-data phase, P8b.
- Intervals are Wilson intervals only. No bootstrap is used.
- The guard records the file's SHA-256 and refuses wrong calls. It cannot stop a person from changing the configuration and running again.
