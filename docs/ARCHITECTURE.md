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
