# VeritasQA — Progress and Handoff

> **Read this file first in every new session.** It is the source of truth for what is done, what is blocked and what comes next. The requirements are in [`docs/SPEC.md`](docs/SPEC.md); design decisions are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## How to resume (after `/clear`)

Say **"continue"**. Then work through the first phase below whose status is `not started` or `in progress`, and follow the per-phase workflow.

| Item | Value |
| --- | --- |
| Git root (working tree) | `E:\Personal\VeritasQA` |
| Remote | `https://github.com/0DevDutt0/VeritasQA.git` (public), branch `main` |
| Project Python (venv) | `E:\Personal\VeritasQA\VeritasQA\Scripts\python.exe` (Python 3.12.10, SQLite 3.49.1 with FTS5). Git-ignored. |
| Full test command | `E:\Personal\VeritasQA\VeritasQA\Scripts\python.exe -m pytest -q` (run from the repo root in Git Bash: `/e/Personal/VeritasQA/VeritasQA/Scripts/python.exe -m pytest -q`) |
| Clean-venv check | Build a fresh venv under the session scratchpad, then `python -m pip install -r requirements.txt` and run the tests there. |
| Git flow per phase | Branch `phase/pN-<name>` from `main` → commit → `git push -u origin phase/pN-<name>` → `git checkout main` → `git merge --ff-only phase/pN-<name>` → `git push origin main` |
| Git auth | Git Credential Manager is the system helper. If a push asks for credentials, set `GIT_TERMINAL_PROMPT=0` and retry with `-c credential.helper='!gh auth git-credential'`. The `gh` CLI is logged in as `0DevDutt0`. |
| Git commands | Use `git -C /e/Personal/VeritasQA ...` with absolute paths. |
| Commit attribution | Every commit message ends with `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`. |
| Scratch files | Use the session scratchpad, not the repo. |

**Per-phase workflow (SPEC §14, repeated for every phase):**
1. Inspect the existing code and this file.
2. Define interfaces and data contracts (update `docs/ARCHITECTURE.md` first if a contract changes).
3. Implement the smallest complete solution. No placeholder modules.
4. Add unit and integration tests.
5. Run the phase's exit-criteria command and the full suite. Record the actual summary line here.
6. Inspect failures. Fix them. Add a regression test for every false answer found.
7. Update this file: status, pytest result, limitations.
8. Commit, push the branch, fast-forward `main`, push `main`.
9. End the turn with a short handoff: the `/clear` instruction and the next phase.

**Owner's workflow instructions (from the request):**
1. Push the work to `https://github.com/0DevDutt0/VeritasQA` at the end of every phase.
2. Use `/clear` after each phase. Keep the upcoming work and the completed/not-completed status in this file, so each phase resumes cleanly from here.
3. The global UI workflow (`~/.claude/CLAUDE.md`, UI/UX Pro Max and Playwright) applies only to frontend work. VeritasQA V1 has no UI (`SPEC §14`: do not build a UI prematurely), so it does not apply yet. Once a UI exists, any visual check of the owner's PDF pages goes through the `screenshot-intake` subagent, not through the main session.

## Status overview

| Phase | Name | Status | Exit-criteria command |
| --- | --- | --- | --- |
| P0 | Repository foundation, plan and architecture | complete | `pytest -q tests/unit/test_p0_foundation.py` |
| P0-ENV | Environment bootstrap: CUDA torch, optional packages, pinned model artifacts (inserted before P1; see D11) | complete-with-limitations | `pytest -q` (full suite), `scripts/validate_environment.py`, `scripts/validate_gpu.py`, `scripts/validate_models.py` |
| P1 | PDF ingestion, extraction and page quality | not started | `pytest -q tests/unit/test_p1_*.py tests/integration/test_p1_*.py` |
| P2 | Structure reconstruction, provenance and segmentation | not started | `pytest -q tests/unit/test_p2_*.py tests/integration/test_p2_*.py` |
| P3 | SQLite schema, FTS5 and exact phrase retrieval | not started | `pytest -q tests/unit/test_p3_*.py tests/integration/test_p3_*.py` |
| P4 | BM25 retrieval and candidate ranking | not started | `pytest -q tests/unit/test_p4_*.py tests/integration/test_p4_*.py` |
| P5 | Question analysis and extractive selection | not started | `pytest -q tests/unit/test_p5_*.py tests/integration/test_p5_*.py` |
| P6 | Evidence verification and citations | not started | `pytest -q tests/unit/test_p6_*.py tests/integration/test_p6_*.py` |
| P7 | Conflict detection, decision engine and abstention | not started | `pytest -q tests/unit/test_p7_*.py tests/integration/test_p7_*.py` |
| P8a | Evaluation harness, metrics and regression framework (synthetic) | not started | `pytest -q tests/unit/test_p8_*.py tests/integration/test_p8_*.py tests/regression` |
| P8b | Real gold dataset (owner's PDF) | **blocked** (B1, B3) | — |
| P9a | Benchmark harness and dev-split sweeps (synthetic) | not started | `pytest -q tests/unit/test_p9_*.py` |
| P9b | Acceptance calibration on real data and held-out evaluation | **blocked** (B1, B3) | — |
| P10 | CLI and multi-document readiness | not started | `pytest -q tests/unit/test_p10_*.py tests/integration/test_p10_*.py` |

Status values: `not started`, `in progress`, `complete`, `complete-with-limitations`, `blocked`. A phase is marked complete only after its exit-criteria command has passed and the result is recorded below.

## Blockers

| ID | Blocker | Affects | What unblocks it |
| --- | --- | --- | --- |
| **B1** | The owner's ~100-page PDF has not been supplied. `data/documents/` is empty. | DoD items 1 and 9; P8b; P9b; any real-document claim | Place the PDF in `data/documents/` (it is git-ignored) and tell the assistant its file name. |
| **B2** | Tesseract OCR is not installed on this machine (`tesseract` is not on PATH). | Real OCR validation (P1); OCR-edge questions (P8) | Optional: install Tesseract (for example `winget install UB-Mannheim.TesseractOCR`), then re-run. OCR code is guarded and tested with a stub until then. |
| **B3** | Gold annotations must be made by hand from the owner's PDF (`SPEC §11`). They cannot be generated or inferred. | P8b; P9b | The owner annotates the questions, or supplies them with exact source quotations, page numbers and split labels. |

## Open questions for the owner

- **Q1.** Provide the PDF (see B1).
- **Q2.** The repository is public. Gold annotations quote the source PDF, which may be copyrighted. Should `data/evaluations/gold/` be committed (the current default) or kept local (git-ignored)?
- **Q3.** Should Tesseract be installed for real OCR validation (see B2)?
- **Q4.** PyMuPDF is AGPL-3.0 or commercially licensed (see `docs/ARCHITECTURE.md` §8). Is that acceptable for a public repository?
- **Q5.** P0-ENV was run as an inserted environment phase, from the "Phase 0 execution instructions" supplied on 2026-11-04 (D11). Confirm that reading. Confirm also that the GPU and experimental groups and the two downloaded models stay in the project venv until a benchmark decides their use (D12, D13).

## Decisions log

| ID | Decision | Reason |
| --- | --- | --- |
| D1 | Git root is `E:\Personal\VeritasQA`. The project venv lives in `VeritasQA/` inside it and is git-ignored. | The owner created the repo at that path. The venv name matches the folder name. |
| D2 | One branch per phase, fast-forward merged into `main`. | Keeps `main` clean. Each phase stays reviewable. The default-branch rule is respected. |
| D3 | PyMuPDF pinned to `1.26.6`. | The 1.26.6 wheel has no dependencies. 2.x pulls in onnxruntime, numpy and a layout/LLM-markdown stack that the baseline does not need. |
| D4 | `pdf_page` is 1-based physical; `printed_page` is the PDF label, kept separate. | `SPEC §3A` requires the two to be separate. |
| D5 | Evidence IDs are deterministic: `{document_id}:p{page}:u{ordinal}`. | Stable citations and reproducible evaluation. |
| D6 | No placeholder modules. Each package appears in the phase that first needs it. | `SPEC §15`. |
| D7 | Source PDFs (`*.pdf`) are never committed. Generated extraction and index data are not committed. | Confidentiality and reproducibility. |
| D8 | UTF-8 everywhere through `app/common/files.py`. LF newlines on output, enforced in the repository by `.gitattributes` (`* text=auto eol=lf`). | Windows defaults to cp1252 and to CRLF with `core.autocrlf`. |
| D9 | No CI workflow yet. | Not requested. Can be added later as a separate phase task. |
| D10 | Dependencies are pinned in `requirements.txt` and validated in a clean venv. | Reproducibility (`SPEC §13`). |
| D11 | The "Phase 0 execution instructions" (2026-11-04) run as an inserted environment phase, **P0-ENV**, before P1. SPEC P0 stays complete. | Those instructions cover environment work the SPEC does not list. SPEC P0 is already done, and the instructions say not to start P1. |
| D12 | Layering. `requirements.txt` is unchanged. GPU and experimental packages live in separate files, installed into the same venv. No pipeline module imports them. | SPEC §1 and §4 keep optional components out of the baseline until a benchmark justifies them. SPEC §13 recommends spaCy/NLTK, so they are validated, not wired in. |
| D13 | Two models are downloaded and validated, not benchmarked, each pinned to a Hub commit: `sentence-transformers/all-MiniLM-L6-v2` (embedder) and `cross-encoder/ms-marco-MiniLM-L6-v2` (reranker). Adoption is gated on P9a. | The instructions name one embedder and one cross-encoder and require load and inference tests. SPEC §4 requires a benchmark before use. |
| D14 | Downloads go to `models/.hf-home` and `models/nltk_data`. The user-level `HF_HOME` (`E:\Personal\AI-Models\huggingface`) is not written. | Every artifact stays in the project, where the ignore rules cover it. The shared cache is left alone. |
| D15 | `VERITASQA_DEVICE` (`auto`, `cuda`, `cpu`) is read from the process environment only. Invalid values raise. `cuda` never falls back silently. | The instructions require an actionable error for explicit CUDA. Reading `.env` would add a dependency and a hidden configuration source. |
| D16 | torch is pinned to `2.14.1+cu130`. torchvision and torchaudio are not installed. | The cu130 index tops out at 2.14.1, while PyPI lists 2.15.0 with a CPU-only Windows wheel. No code uses torchvision or torchaudio. |

---

## Phase details

### P0 — Repository foundation, plan and architecture

- **Status:** complete
- **Branch:** `phase/p0-foundation`, fast-forward merged into `main` (see `git log`, commit message starting `P0:`)
- **SPEC pointers:** §13 (architecture), §14 (P0), §15 (development behaviour), §2 (principles)
- **Done:**
  - Inspected the repository (it contained only `README.md` with an initial commit) and the project venv (empty, Python 3.12.10).
  - Created `.gitignore` before the first `git add`, and verified it with `git check-ignore` (`VeritasQA/` is ignored).
  - Saved the master specification verbatim as `docs/SPEC.md`.
  - Wrote `docs/ARCHITECTURE.md`: pipeline map, data contracts, retrieval and verification principles, storage schema plan, dependency rationale, risks.
  - Pinned dependencies in `requirements.txt` and `pyproject.toml`. Found that PyMuPDF 2.1 pulls in a large unneeded stack, and pinned `1.26.6` instead.
  - Implemented real P0 code: `app/common/errors.py`, `app/common/files.py` (UTF-8 helpers), `app/storage/fts5.py` (FTS5, phrase and `bm25()` startup probe).
  - Added `tests/unit/test_p0_foundation.py` (7 tests).
- **Interfaces exposed:** `app.common.errors.{VeritasQAError, StorageError}`; `app.common.files.{read_text, write_text, read_json, write_json}`; `app.storage.fts5.{ensure_fts5_available, fts5_available}`.
- **Exit criteria:** `pytest -q tests/unit/test_p0_foundation.py`
- **Result:**
  - Project venv (Python 3.12.10, SQLite 3.49.1): `7 passed in 0.21s`
  - Clean venv built from `requirements.txt`: `7 passed in 0.13s`, `pip check`: "No broken requirements found."
- **Limitations:**
  - No document is processed yet (B1). No real PDF is available.
  - The FTS5 probe confirms the build supports FTS5. It does not measure retrieval quality.
  - Ingestion, storage and retrieval modules are not implemented yet, by design.

### P0-ENV — Environment bootstrap, CUDA validation and pinned model artifacts (inserted before P1)

- **Status:** complete-with-limitations
- **Reading taken (D11):** the "Phase 0 execution instructions" of 2026-11-04 describe an environment phase. The SPEC's P0 (repository foundation) was already complete, so this phase is recorded as P0-ENV and run before P1. P1 is not started. Q5 asks the owner to confirm this reading.
- **Branch:** `phase/p0-env-bootstrap`, fast-forward merged into `main`.
- **SPEC pointers:** §1 (constraints), §4 (optional components, benchmark-gated), §9 (calibration), §13 (dependencies), §15 (behaviour)
- **Done:**
  - Inspected before changing anything. The venv was Python 3.12.10 with the P0 pins only, and `pip check` was clean. The baseline tests passed (7). Two `python` processes running `ai_update` belong to another tool and were left running. The pip cache held 17 GB. `HF_HOME` is `E:\Personal\AI-Models\huggingface`, which holds 389 model repos, and neither chosen model was among them. No stray `.whl`, `.incomplete` or interrupted-install files existed. PyPI, the PyTorch index, Hugging Face and GitHub were reachable.
  - `.gitignore`: added `models/**` (with `models/README.md` and `models/manifests/**` re-included), the weight formats, `.env` and `.env.*` (with `.env.example` re-included), and `nltk_data/`. Confirmed with `git check-ignore` before any download.
  - Installed `torch==2.14.1+cu130` into the project venv, after a dry run, with no torchvision or torchaudio.
  - Installed the experimental group under `-c requirements.txt -c constraints-gpu.txt`: numpy 2.5.4, scikit-learn 1.9.1, spacy 3.8.18, nltk 3.10.4, rapidfuzz 3.14.6, sentence-transformers 6.2.0, huggingface-hub 2.4.0 (plus their dependencies). A freeze diff from before to after the installs shows only additions and no version changes.
  - Downloaded the two models pinned to Hub commits. Every file was checked against the Hub's own digest, and manifests were written to `models/manifests/`. Fetched only the NLTK `punkt_tab` resource.
  - Code: `app/common/device.py` (the `VERITASQA_DEVICE` resolver, the GPU report and a CUDA matmul smoke test), `app/common/models.py` (manifest checks, the non-generative check and the embedder and reranker smoke tests), and `scripts/download_models.py`, `validate_environment.py`, `validate_gpu.py`, `validate_models.py`. No module under the pipeline imports any of them.
  - Tests: `tests/unit/test_p0env_device.py` (20), `tests/unit/test_p0env_manifests.py` (5), `tests/integration/test_p0env_gpu.py` (3), `tests/integration/test_p0env_models.py` (4), `tests/integration/test_p0env_nlp.py` (2). `tests/conftest.py` skips `requires_cuda` and `requires_models` tests with a stated reason. Both markers are registered in `pyproject.toml`.
  - Files: `requirements-gpu.txt`, `constraints-gpu.txt`, `requirements-experimental.txt`, `requirements-validated.txt` (full lock, 82 packages), `.env.example`, `models/README.md`, `models/manifests/*.json`, `docs/SETUP.md`. Updated: the header of `requirements.txt` (the stale "not included on purpose" text is removed), `docs/ARCHITECTURE.md` §7 and §9, and `README.md`.
- **Interfaces exposed:** `app.common.device.{ENV_VAR, DeviceConfigError, DeviceUnavailableError, CudaProbe, probe_cuda, resolve_device, gpu_report, cuda_matmul_smoke_test}`; `app.common.models.{sha256_file, git_blob_sha1, load_manifest, non_generative_problems, verify_manifest, smoke_test_embedder, smoke_test_reranker}`.
- **Exit criteria:** `pytest -q` (full suite, including `tests/unit/test_p0env_*.py` and `tests/integration/test_p0env_*.py`), and `scripts/validate_environment.py`, `scripts/validate_gpu.py` and `scripts/validate_models.py` each exit 0.
- **Result (recorded from runs):**
  - Project venv, full suite: `41 passed in 7.08s`, 0 skipped.
  - Clean baseline venv (`requirements.txt` only, no torch): `34 passed, 7 skipped in 0.31s`. The skips are the 3 GPU tests, 2 CUDA model tests (no PyTorch) and 2 NLP tests (no spaCy or NLTK).
  - Fresh venv rebuilt from `requirements-validated.txt`: `41 passed in 13.89s`. Its freeze matches the lock exactly (82 packages), and the three validators each exit 0.
  - `validate_environment.py`: `RESULT: baseline valid`. `validate_gpu.py`: `RESULT: GPU validated`. `validate_models.py`: `RESULT: all model checks passed`.
  - Fresh-clone simulation (tracked files only, no weights, not a git repo, baseline venv): `32 passed, 9 skipped`, with no failures.
- **Installed / Downloaded / Loaded / Validated:**

| Item | Installed | Downloaded | Loaded | Validated |
| --- | --- | --- | --- | --- |
| torch 2.14.1+cu130 (CUDA 13.0) | yes | n/a (wheel) | CUDA device opened on NVIDIA GeForce RTX 5090 Laptop GPU (sm_120) | kernel check: float32 matmul on GPU vs CPU, relative error 9.64e-07 |
| numpy, scikit-learn, rapidfuzz | yes | n/a | imports only | import only; no pipeline use yet |
| spaCy 3.8.18 | yes | n/a | `spacy.blank("en")` with sentencizer | segmentation test passes |
| NLTK 3.10.4 with `punkt_tab` | yes | yes: 77 files, 10,885,330 bytes, plus the 4,319,076-byte archive; digests not verified by this project | `sent_tokenize` runs | NLTK test passes |
| sentence-transformers 6.2.0, transformers 5.22.1 | yes | n/a | used by both model tests | both model tests pass |
| all-MiniLM-L6-v2 (embedder) | yes, under `models/` | yes: 11 files, 91,578,415 bytes, each file matched to the Hub digest | from the local path, Hub offline, `cuda:0` | output shape (3, 384), all finite, minimum cosine against CPU 1.000000 |
| ms-marco-MiniLM-L6-v2 (reranker) | yes, under `models/` | yes: 7 files, 91,819,431 bytes, each file matched to the Hub digest | from the local path, Hub offline, `cuda:0` | output shape (2,), all finite, maximum score difference against CPU 2.86e-06 |
| Tesseract OCR (B2) | no | no | no | not attempted; left as it was |

- **Limitations:**
  - Both models are validated for download, digest, non-generative architecture, loading and inference. Neither is benchmarked. Neither may enter the pipeline before P9a shows a gain over the BM25 baseline (SPEC §4, §9).
  - The GPU is a laptop RTX 5090 with 24,463 MiB. All measurements were taken on this device.
  - GPU memory is shared with an Ollama `llama-server` (PID 31904). At the same moment, `nvidia-smi` reported 5,768 MiB free and `torch.cuda.mem_get_info()` reported 23,119 MiB. The cause was not established. Every test allocation is under 0.5 GB, so the results do not depend on the choice.
  - Not tested: training, mixed precision, multiple GPUs, and a second CUDA build for comparison.
  - The NLTK resource is not checked against digests by this project.
  - No Tesseract and no GPU OCR library were installed. B2 is unchanged.
  - The optional groups are not used by any pipeline module, so their behaviour in the pipeline is unvalidated.
- **Reproducibility:** `docs/SETUP.md` §3 and §6. The baseline was rebuilt from scratch in a clean venv. The whole validated environment, including the GPU and experimental groups, was rebuilt from scratch from `requirements-validated.txt`.

### P1 — PDF ingestion, extraction and page-level quality validation

- **Status:** not started
- **SPEC pointers:** §3A (ingestion and extraction), §12 (integrity, reading order, multi-column, OCR source handling), §16 DoD 2
- **Scope:**
  - **Validation:** the file exists and is non-empty, is under a configured size limit, starts with `%PDF-`, opens with PyMuPDF, is not encrypted (or fails with an explicit error), has at least one page, and yields a SHA-256 for the `document_id` (D5/§3 of ARCHITECTURE).
  - **Extraction:** per page, with PyMuPDF `get_text("dict")`, collect blocks, lines and spans (text, bbox, font size, bold flag, font name), image blocks and image areas, and the printed page label. Do not trust PDF text as instructions; do not execute embedded content.
  - **Quality classification (documented heuristics, not acceptance thresholds):** `BLANK` (no text, and a low-DPI render has almost no ink), `SCANNED` (no text but large image coverage), `GARBLED` (replacement or private-use or control characters above a limit), `SUSPICIOUS` (letter ratio or single-character token ratio is unusual), `WARNING` (usable but flagged), `OK`. Every decision is recorded as a warning with its reason.
  - **Reading order:** cluster blocks into columns by horizontal overlap; read columns left to right, top to bottom. Identify repeated header and footer text across at least half of the pages. Flag every page where order is uncertain. Never assume the extracted order is visual order.
  - **Tables:** flag pages where pdfplumber detects tables. Cell extraction belongs to P2.
  - **Rendering:** render suspicious pages to PNG for inspection (`render_page_png`). Any visual review of the owner's pages goes through `screenshot-intake`.
  - **OCR:** a Tesseract CLI adapter that runs only when `tesseract` is on PATH, using an argument list and no shell. OCR text is tagged `ocr_tesseract` with quality `unverified`. Without the binary, scanned pages stay `SCANNED` with an `ocr_unavailable` warning.
  - **Output:** an extraction report per document, written to `data/extracted/<document_id>/extraction_report.json` (UTF-8, via `app/common/files.py`), plus the immutable `raw_text` per page.
- **Interfaces to expose:** `app.ingestion.validate_pdf(path) -> PdfFileInfo`; `app.ingestion.extract_document(path) -> ExtractedDocument`; `app.ingestion.classify_page(...)`; `app.ingestion.render_page_png(path, pdf_page, dpi, out_path)`; `app.ingestion.ocr.tesseract_available()`, `app.ingestion.ocr.ocr_page(...)`; `config/default.toml` `[ingestion]` section.
- **Test plan:** synthetic PDFs generated by the tests with PyMuPDF (labelled synthetic). Cover: invalid and truncated files, encrypted files, blank page, image-only page, garbled text, a two-column layout (reading order), repeated headers and footers, printed page labels, a page with a ruled table, Unicode text (non-ASCII round-trip). OCR: a stubbed-binary test always runs; a real-binary test is marked `requires_tesseract`.
- **Exit criteria:** `pytest -q tests/unit/test_p1_*.py tests/integration/test_p1_*.py`
- **Result:** not run yet
- **Limitations (expected):** heuristic reading order; OCR unverified on this machine (B2); no real document (B1).

### P2 — Structure reconstruction, provenance and evidence segmentation

- **Status:** not started
- **SPEC pointers:** §3B (structure and segmentation), §2.3 (provenance), §6 (answer context), §16 DoD 3
- **Scope:**
  - **Normalization (reversible):** `app/common/text.py` `normalize_with_map(raw) -> NormalizedText(text, index_to_raw)`. NFKC per character, with each output character mapped back to its raw offset. Unify quote and dash variants, map NBSP to space, remove soft hyphens, and dehyphenate line-end breaks in index text only. Test ligatures, NBSP, soft hyphen, curly quotes, combining marks, CJK, Arabic (RTL).
  - **Headings:** body font size from the character-weighted size mode; headings are larger or bold short lines; the hierarchy comes from the ranks of the heading sizes. Produce `sections` with parent links.
  - **Units:** paragraphs (wrapped lines merged, offsets kept into `raw_text`), list items attached to their intro (`parent_id`), captions (`Table n` / `Figure n`) attached to their table, footnotes from the bottom band, and header/footer units kept but excluded from body retrieval by a flag.
  - **Tables:** pdfplumber cells with a header row. Each cell becomes a unit carrying `row_header`, `col_header`, `caption`, `table_id`, `row_index` and `col_index`. Each row also gets a unit whose text states the header-value pairs, so a number is never indexed without its row and column.
  - **Neighbours:** `prev_id`, `next_id`, `section_id`, `parent_id`, bounding box, `content_type`, inherited `extraction_quality`.
- **Interfaces to expose:** `app.common.text.normalize_with_map`; `app.document_structure.build_structure(extracted) -> DocumentStructure(sections, units, table_cells)`; `EvidenceUnit` (Pydantic) with the fields in ARCHITECTURE §3.
- **Exit criteria:** `pytest -q tests/unit/test_p2_*.py tests/integration/test_p2_*.py`
- **Result:** not run yet
- **Limitations (expected):** heading detection depends on font metadata; scanned or garbled pages produce no reliable structure.

### P3 — SQLite schema, FTS5 and exact phrase retrieval

- **Status:** not started
- **SPEC pointers:** §3C (storage), §4 (exact phrase, escaping), §12 (escaping and SQL safety), §16 DoD 4
- **Scope:**
  - `app/storage/schema.py` creates the tables in ARCHITECTURE §6 (`documents`, `pages`, `sections`, `source_locations`, `evidence_units`, `table_cells`, `evidence_fts`, `evaluations`). Checks FTS5 at open (`ensure_fts5_available`).
  - `app/storage/repository.py` writes and reads with parameterized SQL only, scoped by `document_id`.
  - `app/retrieval/query.py` builds FTS5 queries from tokens quoted with a fixed pattern. The query is kept reversibly beside the source text.
  - `app/retrieval/phrase.py` runs an FTS5 phrase query for candidates, then applies a deterministic check on normalized text (`3.5` must not match `3 5` or `3 . 5` by accident).
- **Interfaces to expose:** `app.storage.Store` (open, check FTS5, write document, query); `app.retrieval.phrase.find_phrase(store, document_id, phrase) -> list[EvidenceUnit]`.
- **Test plan:** FTS5-syntax characters (`"`, `*`, `:`, `^`, `-`, `NEAR(`, `AND`, `OR`, parentheses) and SQL-injection strings must be harmless. Phrase vs. adjacency. Unicode queries. Two documents in one database must not leak results across `document_id`.
- **Exit criteria:** `pytest -q tests/unit/test_p3_*.py tests/integration/test_p3_*.py`
- **Result:** not run yet
- **Limitations (expected):** none specific to the baseline.

### P4 — BM25 retrieval and candidate ranking

- **Status:** not started
- **SPEC pointers:** §4 (BM25, heading-aware, numeric preservation, K, duplicates, expansion), §9 (do not expose scores as probability), §12 (BM25 ranking direction), §16 DoD 4
- **Scope:**
  - `app/retrieval/bm25.py`: `ORDER BY bm25(evidence_fts, w_text, w_heading) ASC LIMIT K` with rank assigned from position. The raw BM25 value is stored separately and never shown as a probability.
  - Heading-aware weights, read from config.
  - `app/retrieval/terms.py`: extract numeric, date and identifier terms (for example `3.5`, `10%`, `2024-01-01`, `ABC-123`) so verification can check them later.
  - Duplicate removal by hash of normalized text. Expansion adds neighbours and section siblings as context only and never replaces evidence.
  - RRF is not implemented. It is added only if a benchmark shows a gain (P9).
- **Interfaces to expose:** `app.retrieval.bm25.search(store, document_id, query, k, weights) -> list[RetrievalCandidate]`.
- **Exit criteria:** `pytest -q tests/unit/test_p4_*.py tests/integration/test_p4_*.py`
- **Result:** not run yet
- **Limitations (expected):** lexical only; synonyms and paraphrases are missed by design.

### P5 — Question analysis and extractive selection

- **Status:** not started
- **SPEC pointers:** §5 (question processing), §6 (extractive answer selection), §12 (numeric and unit extraction, negation, entity mismatch, compound questions)
- **Scope:**
  - `app/question_processing/analysis.py`: deterministic analysis into a `QuestionAnalysis`: type (`WHAT`, `WHO`, `WHEN`, `WHERE`, `HOW_MANY`, `WHICH`, `WHETHER`, `CONDITIONS`, `COMPARISON`, `UNSUPPORTED`), target terms, attribute terms, numeric and date intent, negation, conditions, scope, and compound components. Ambiguous or unsupported input is flagged, not guessed.
  - `app/evidence/values.py`: numbers with units, percentages, currency, dates, periods (for example `2019–2021`), with exact spans.
  - `app/evidence/selection.py`: sentence segmentation (abbreviation-aware), then per-type candidate spans. Each candidate records the rule that produced it (`rule_id`). No paraphrase is produced.
  - Compound questions: each component is analysed and selected separately.
- **Interfaces to expose:** `app.question_processing.analyze(question) -> QuestionAnalysis`; `app.evidence.select_candidates(analysis, units) -> list[AnswerCandidate]`.
- **Exit criteria:** `pytest -q tests/unit/test_p5_*.py tests/integration/test_p5_*.py`
- **Result:** not run yet
- **Limitations (expected):** rules cover the supported question types only.

### P6 — Evidence verification and citations

- **Status:** not started
- **SPEC pointers:** §7 (the eleven checks, quotation integrity is not semantic support), §10 (evidence record), §12 (provenance, negation, entity mismatch), §16 DoD 6
- **Scope:**
  - `app/verification/checks.py`: one function per check (1 quotation integrity, 2 location integrity, 3 answer-span integrity, 4 entity, 5 attribute, 6 value, 7 context, 8 negation, 9 condition, 10 conflict screening (calls P7 later), 11 source quality). Each returns `PASS`, `FAIL`, `UNRESOLVED` or `NOT_APPLICABLE`, with a reason.
  - `app/verification/verifier.py`: explicit required-check lists per question type. A candidate passes only when every required check is `PASS`.
  - Context uses neighbours without changing the evidence. Exception and qualifier markers (`except`, `unless`, `only if`, `provided that`, `does not apply`, `however`) make the result `UNRESOLVED`.
- **Interfaces to expose:** `app.verification.verify(candidate, analysis, store, document_id) -> VerificationReport`.
- **Exit criteria:** `pytest -q tests/unit/test_p6_*.py tests/integration/test_p6_*.py`
- **Result:** not run yet
- **Limitations (expected):** semantic support is only partly testable by rules; ambiguous cases stay `UNRESOLVED`.

### P7 — Conflict detection, decision engine and abstention

- **Status:** not started
- **SPEC pointers:** §8 (conflicts), §9 (decision outcomes, acceptance policy), §10 (response contract), §12 (conflicting evidence, abstention), §16 DoD 7 and 8
- **Scope:**
  - `app/conflict/detector.py`: fact keys (entity, attribute, unit, scope, effective date). Relations: `SAME_VALUE`, `DIFFERENT_SCOPE`, `DATED_CHANGE`, `EXPLICIT_SUPERSESSION`, `POTENTIAL_DISCREPANCY`, `CONFIRMED_INCOMPATIBLE`. Numbers that differ across different scopes are never called conflicts. Precedence applies only when the document states it, and the supersession phrases are a tested, configured list.
  - `app/decision/engine.py`: the six statuses from `SPEC §9`. `PARTIAL` reports each component separately.
  - `config/acceptance_policy.toml`: boolean gates only (for example `require_negation_validation = true`), with no similarity thresholds. Defaults are conservative and marked uncalibrated.
  - `app/decision/response.py`: Pydantic `QAResponse` following `SPEC §10`, with validated enums. Retrieval scores, verification results and decision reasons are separate sections.
- **Interfaces to expose:** `app.decision.answer(store, document_id, question, policy) -> QAResponse`.
- **Exit criteria:** `pytest -q tests/unit/test_p7_*.py tests/integration/test_p7_*.py`
- **Result:** not run yet
- **Limitations (expected):** the default gates are not calibrated on real data (P9b).

### P8a — Evaluation harness, metrics and regression framework (synthetic)

- **Status:** not started
- **SPEC pointers:** §11 (evaluation), §12 (regression tests), §16 DoD 9 and 10
- **Scope:**
  - `app/evaluation/gold.py`: Pydantic schema for gold JSONL records (question, type, expected answerability, expected status, gold evidence with page and exact quotation, gold answer spans, split `dev` or `heldout`, annotator). Validation rejects records with inexact quotations.
  - Split enforcement: `heldout` runs require an explicit `--final-run` flag, and the runner records the SHA-256 of the gold file used.
  - `app/evaluation/metrics.py`: Recall@K, Precision@K, MRR, nDCG, Exact Match, token F1, false acceptance rate, correct and incorrect abstention, coverage, selective risk, risk-coverage curve, Wilson confidence intervals.
  - `app/evaluation/runner.py`: writes run results to `data/evaluations/runs/` (git-ignored) and to the `evaluations` table.
  - `tests/regression/`: one case per discovered false answer. The file `tests/regression/known_failures.jsonl` starts empty and grows over time.
  - Synthetic fixtures are used for unit tests only. They are labelled `synthetic` and are never reported as results about the owner's document.
- **Exit criteria:** `pytest -q tests/unit/test_p8_*.py tests/integration/test_p8_*.py tests/regression`
- **Result:** not run yet

### P8b — Real gold dataset (owner's document) — **blocked (B1, B3)**

- **Status:** blocked
- **Needed:** the owner's PDF in `data/documents/`, and about 120 manually annotated questions under `data/evaluations/gold/` (development and held-out splits). The categories are listed in `SPEC §11`.
- **Rule:** the assistant never invents ground-truth facts.

### P9a — Benchmark harness and dev-split sweeps (synthetic)

- **Status:** not started
- **SPEC pointers:** §9 (calibration rules), §11 (held-out separation), §16 DoD 9
- **Scope:** a sweep harness over K, neighbour window and heading weight, run on the dev split only. It reports results and never writes calibrated values into the policy file. RRF, TF-IDF and embeddings are benchmarked only if the lexical baseline falls short on the real gold set.
- **Exit criteria:** `pytest -q tests/unit/test_p9_*.py`
- **Result:** not run yet

### P9b — Calibration on real data and held-out evaluation — **blocked (B1, B3)**

- **Status:** blocked
- **Needed:** P8b. Calibrate the gates on the development split only. Run the held-out split once, record it, and document the limitations and confidence intervals.

### P10 — CLI and multi-document readiness

- **Status:** not started
- **SPEC pointers:** §13 (CLI or API as an optional adapter), §14 (P10), §16 DoD 12
- **Scope:** `app/api/cli.py` (argparse) with `ingest`, `ask`, `report` and `evaluate` subcommands and JSON output. Queries are scoped by `document_id`. Two-document tests show there is no cross-document leakage. FastAPI is not added unless there is a concrete need. The README gets a reproducible setup section and the limitations.
- **Exit criteria:** `pytest -q tests/unit/test_p10_*.py tests/integration/test_p10_*.py`
- **Result:** not run yet

---

## Definition of Done (SPEC §16) — current state

| # | Item | State |
| --- | --- | --- |
| 1 | 100-page PDF processed and indexed | blocked (B1) |
| 2 | Extraction issues detected and exposed | P1 |
| 3 | Evidence provenance accurate | P2 |
| 4 | BM25 and exact phrase retrieval reliable | P3, P4 |
| 5 | Supported answer types use extractive selection | P5 |
| 6 | Exact quotations and page citations verifiable | P6 |
| 7 | Unsupported questions trigger abstention | P7 |
| 8 | Conflicts exposed, not resolved silently | P7 |
| 9 | Evaluation metrics from manually verified data | blocked (B3); harness P8a |
| 10 | Regression tests for discovered failures | P8a (framework), grows as failures are found |
| 11 | Critical functionality runs without a generative LLM | Holds by design; enforced by the dependency list |
| 12 | Documentation explains limitations and reproducible setup | P10 (README), ARCHITECTURE §8–9 |
