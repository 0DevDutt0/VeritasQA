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
- Queries are never passed to FTS5 unquoted. Each query token is extracted by a fixed pattern and wrapped as a quoted FTS5 string. All values are bound as SQL parameters.
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
- **Retrieval expansions never count as support.** A synonym or stem match can only add a candidate. The entity, value, negation and condition checks read raw text and must find the question's terms in it. An expansion that does not appear in the raw text leads to abstention, which is the intended conservative outcome. Whether reviewed rules may ever count toward acceptance is an open owner decision (Q9 in `PROGRESS.md`). The default is no.

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
