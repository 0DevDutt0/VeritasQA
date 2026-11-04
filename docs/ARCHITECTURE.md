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
- Heading text sits in a separate FTS5 column so its weight can be tuned (P4).
- Reciprocal Rank Fusion is not implemented. It is added only if a measured benchmark shows a gain (`SPEC §4`).
- Candidate depth K is configurable. Recall is measured at several K values; top-3 is never assumed sufficient.
- **Controlled synonym and stemming rules (P4, D17).** Recall only. The rules live in a versioned data file (planned `config/retrieval_rules.toml`). Each rule has an ID, a version, positive examples, counter-examples and a reviewer note. Expansion is query-time and one-way: a query term may add listed alternatives, and the index is never rewritten. Each expansion is recorded in the retrieval trace with its rule ID. Expanded matches only add candidates. The entity, value, negation and condition checks (§5) run on raw text and cannot be satisfied by an expansion alone.
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
- No stemming, synonyms or ranking. Those belong to P4. The FTS5 index uses the default unicode61 tokenizer.
- CJK text without spaces forms long token runs. A phrase inside a run is not found (`文字` does not find `文字の認識`), but a phrase equal to a whole run is found. Substring retrieval for CJK needs another tokenizer, which V1 does not plan.
- Case folding means `US` also finds `us`. P5 and P6 decide entity and value matches. P3 only proposes candidates.
- A phrase copied from a table row's generated `index_text`, with its ` | ` or ` = ` glue, is not found. This is by design.
- BM25 statistics are index-wide, because all documents share one FTS table. A second document changes the scores of the first. This is a P4 concern (see the P4 handoff).
- **A private-use character glued to a word hides the word.** `abcd` is one token for unicode61 and one word for the exact check, so `ab` and `cd` do not find it (pinned in `test_p3_phrase_check.py`). A symbol-font glyph with no space beside a word has this effect.
- **Derived table rows are found only through the text their generated index states.** P2 writes a row's `index_text` from the cells whose column has a header (§11), and it joins adjacent cells that share one raw line into one span (D28). So a value in a headerless column, or a phrase that crosses a cell boundary, does not find its row. The exact check accepts such a phrase where the span is verbatim, so the gap is a missed candidate, never a false acceptance. The recall test excludes exactly the windows that the row's index does not state: 16 of 481 on the public corpus, all derived rows.

The full corpus gives the size of the gap. 417 of 1,488 derived rows (28.0%) have at least one span that their index does not state, 571 spans in all. Each span falls into one of three groups:
- (a) 204 spans equal the text of one cell of the row. All 204 are found through their cell.
- (b) 330 spans are runs of whole cells, joined by P2's span merging. Each of the 735 constituent cells is found through its own unit. The cross-cell phrase returns the row in 0 of 330 cases, because the index does not state it.
- (c) 37 spans are parts of one cell's text (34, all found through that cell) or partial cross-cell merges (3, not classified further).

So every value is found through a cell unit, and what a derived row loses is only the cross-cell phrase. This is a P2 table-index limit, open as Q12 in `PROGRESS.md`.

- **Case folding follows the index, not Python alone.** On this build (SQLite 3.49.1) the index does not fold 416 of the 1,432 cased single characters in planes 0 and 1 (`index_foldable_characters`). They are mostly Cherokee, Old Hungarian, Georgian Mtavruli, Osage, Vithkuqi, Adlam, Warang Citi and Medefaidrin, with some Latin, Cyrillic, Greek and Glagolitic capitals. For those characters the phrase search is case-sensitive: `Ꭰ` does not find `ꭰ`, and that is a recall miss, never a false acceptance. The calibration follows the SQLite build, so an upgrade changes the set without a code change (`tests/unit/test_p3_case_folding.py`).
- **Recall evidence (P3, public corpus).** `tests/integration/test_p3_corpus.py` cuts whitespace windows from the normalized text of 174 sampled units across eight body content types, including every span of the sampled rows and cells. 465 windows were checked, and each found its own unit; 16 more were excluded as derived-row windows that the index does not state (above). That is recall for the windows the index states. It is not measured recall for the owner's document (B1, B3).
