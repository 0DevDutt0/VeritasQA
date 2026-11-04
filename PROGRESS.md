# VeritasQA — Progress and Handoff

> **Read this file first in every new session.** It is the source of truth for what is done, what is blocked and what comes next. The requirements are in [`docs/SPEC.md`](docs/SPEC.md); design decisions are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## How to resume (after `/clear`)

Say **"continue"**. Then work through the first phase below whose status is `in progress` or `not started`, and follow the per-phase workflow. A phase whose status is `blocked` on an owner decision stops the run: report the open decision and wait. Do not start a later phase.

**Current resume point (2026-11-04, after P3):** P0-REV, P0-CLEAN, P1, P2 and P3 are complete. **P4 is next, and it is blocked on Q9** (the owner's own text: "answer this before P4 is built"). On "continue", if Q9 is still open, report it and wait; do not start P4. Q4 (the PyMuPDF licence), Q8, Q9, Q10 and Q11 are still open. Q3 (install Tesseract) decides whether the OCR path is ever run for real (B2).

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
| P0-ENV | Environment bootstrap: CUDA torch, optional packages, pinned model artifacts (inserted before P1; see D11) | complete-with-limitations; **superseded by D17**; artifacts removed by P0-CLEAN | historical (its validation scripts were removed in P0-CLEAN) |
| P0-REV | V1 revision: deterministic, LLM-free and embedding-free architecture, dependency plan and Phase 0 checklist (D17) | complete | `pytest -q` (full suite), `scripts/validate_environment.py` |
| P0-CLEAN | Owner-approved cleanup of the GPU, model, NLP and fuzzy-matching layers; V1 venv rebuilt and lock regenerated (D19) | complete | `pytest -q` in a fresh V1 venv, `pip check`, deny-list tests (`tests/unit/test_p0_dependencies.py`) |
| P1 | PDF ingestion, extraction and page quality | complete on synthetic PDFs; the real-document check is blocked (B1) and the real OCR check is blocked (B2) | `pytest -q tests/unit/test_p1_*.py tests/integration/test_p1_*.py` |
| P2 | Structure reconstruction, provenance and segmentation | complete-with-limitations (synthetic fixtures and public-corpus property checks pass; structure quality on real documents is unmeasured, B1) | `pytest -q tests/unit/test_p2_*.py tests/integration/test_p2_*.py` |
| P3 | SQLite schema, FTS5 and exact phrase retrieval | complete-with-limitations (synthetic and public-corpus property checks pass; retrieval on real documents is unmeasured, B1) | `pytest -q tests/unit/test_p3_*.py tests/integration/test_p3_*.py` |
| P4 | BM25 retrieval and candidate ranking | **blocked** (Q9: the owner answers it before P4 is built) | `pytest -q tests/unit/test_p4_*.py tests/integration/test_p4_*.py` |
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
- **Q5. Closed by D17.** The owner's 2026-11-04 revision reversed the GPU and model parts of P0-ENV (D12, D13, D16). Their results stay below as history. The inserted-phase reading of P0-ENV (D11) is kept as recorded. Nothing further is asked here.
- **Q6. Closed (2026-11-04, owner).** Remove spaCy, NLTK (with its `punkt_tab` resource) and rapidfuzz from the V1 plan. Keep numpy and scikit-learn as an optional, benchmark-only group outside `requirements.txt` and the acceptance path (D19). P5 is planned as a deterministic, abbreviation-aware splitter. Reintroducing any of these packages needs a new owner decision, and the deny-list test would have to change with it.
- **Q7. Closed (2026-11-04, owner): approved.** P0-CLEAN ran as proposed, with the Q6 choices above. The shared pip cache (18 GB) and the shared Hugging Face cache (9.7 GB) are not project-owned, and they were not touched.
- **Q8. SPEC wording.** Keep `docs/SPEC.md` verbatim with the repository precedence note (D18), or re-issue the specification with the V1 revision? Recommendation: keep it verbatim.
- **Q9. Synonym rules and acceptance.** The default stays conservative. An expansion can widen the candidate set, but it cannot satisfy the entity, value, negation or condition checks, which run on raw text (`docs/ARCHITECTURE.md` §4 and §5). Should reviewed rules ever count toward acceptance? A yes needs a per-rule flag such as `verification_eligible` (default off), a regression set that shows no false acceptances, and a decision recorded here. Recommendation: keep the default off. Answer this before P4 is built. **Status: open; P4 is blocked on it (status table).**
- **Q10. Public QA corpus (D27).** Should the three public PDFs in `data/corpus/public/` be committed, or kept local? The two NIST documents are US federal works. The licence of the arXiv paper (2506.12594) was not checked. Recommendation: keep the PDFs local (D7) and track only the manifest and the README.
- **Q11. P1 reading-order repair (D31).** Should the repair of P1's column clustering come before P6? P6's context, negation and qualifier checks read `prev_id` and `next_id`, which follow P1's order. Options: (a) repair P1 before P6; (b) accept P1's order for P6 and mark every context-dependent verdict `UNRESOLVED` on a page with `reading_order_uncertain`. Recommendation: (a). It need not block P3 or P4.

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
| D12 | **[Superseded in part by D17: the GPU group is outside V1, and the experimental group is optional.]** Layering. `requirements.txt` is unchanged. GPU and experimental packages live in separate files, installed into the same venv. No pipeline module imports them. | SPEC §1 and §4 keep optional components out of the baseline until a benchmark justifies them. SPEC §13 recommends spaCy/NLTK, so they are validated, not wired in. |
| D13 | **[Superseded by D17: no model is part of V1.]** Two models are downloaded and validated, not benchmarked, each pinned to a Hub commit: `sentence-transformers/all-MiniLM-L6-v2` (embedder) and `cross-encoder/ms-marco-MiniLM-L6-v2` (reranker). Adoption is gated on P9a. | The instructions name one embedder and one cross-encoder and require load and inference tests. SPEC §4 requires a benchmark before use. |
| D14 | **[Superseded in part by D17: no download is part of V1. The rule for the user-level cache still holds.]** Downloads go to `models/.hf-home` and `models/nltk_data`. The user-level `HF_HOME` (`E:\Personal\AI-Models\huggingface`) is not written. | Every artifact stays in the project, where the ignore rules cover it. The shared cache is left alone. |
| D15 | **[Superseded in part by D17: V1 reads no device setting. The rules below applied to the historical GPU layer.]** `VERITASQA_DEVICE` (`auto`, `cuda`, `cpu`) is read from the process environment only. Invalid values raise. `cuda` never falls back silently. | The instructions require an actionable error for explicit CUDA. Reading `.env` would add a dependency and a hidden configuration source. |
| D16 | **[Superseded by D17: PyTorch is outside V1.]** torch is pinned to `2.14.1+cu130`. torchvision and torchaudio are not installed. | The cu130 index tops out at 2.14.1, while PyPI lists 2.15.0 with a CPU-only Windows wheel. No code uses torchvision or torchaudio. |
| D17 | **V1 is deterministic, LLM-free and embedding-free** (owner's change of plans, 2026-11-04). Removed from the V1 dependency and model-download plan: sentence-transformers, embedding models, dense retrieval, cross-encoder rerankers, PyTorch and CUDA, vector databases and generative LLMs. TF-IDF is kept only as an optional, benchmark-only baseline. It is sparse lexical weighting, never an embedding. Controlled synonym and stemming rules are added to P4 as recall-only, versioned and logged. Nothing is uninstalled or deleted until the owner approves the cleanup (Q7). | The owner's directive asks for maximum factual precision, minimum incorrect accepted answers and a light installation. CUDA is not required by the retrieval and verification pipeline. |
| D18 | `docs/SPEC.md` keeps its verbatim body. Where SPEC §4 (optional embeddings and cross-encoder reranking) or SPEC §13 (spaCy and NLTK) differ from D17, D17 governs V1. A repository note in the SPEC header points to this decision. | The SPEC is the owner's text. A change of plan is recorded in the repository, not by rewriting the owner's prompt. Q8 asks the owner to confirm this. |
| D19 | **Owner decisions, 2026-11-04.** Q6: spaCy 3.8.18, NLTK 3.10.4 (with the `punkt_tab` resource) and rapidfuzz 3.14.6 are removed from the V1 plan. numpy and scikit-learn stay as an optional, benchmark-only group outside `requirements.txt` and the acceptance path. Q7: the P0-CLEAN cleanup is approved and was carried out as proposed. | The owner's answers. They are recorded here so that later sessions do not reopen them. `tests/unit/test_p0_dependencies.py` enforces the removals. |
| D20 | **Hidden text layers (P1).** Invisible text (text render mode 3 or 7) is read from `page.get_texttrace()`, because `get_text("dict")` does not expose the mode (probed on PyMuPDF 1.26.6). An image-dominated page whose text has unknown origin is `SCANNED_TEXT_LAYER` (unverified), whether or not its text is invisible. A page whose only text is invisible is `SUSPICIOUS`. A page whose invisible share of its text characters exceeds `hidden_text_share_max` (2%, uncalibrated) is `SUSPICIOUS` (`hidden_text_share_high`). Any smaller invisible share keeps the page below `OK` (WARNING). Each line records its invisible character count (`hidden_chars`), and P2 must not ground an answer on a line whose count is above zero. | A scanned PDF can carry an invisible OCR layer that reads like native text, and an invisible paragraph can sit beside one visible line. SPEC §1 forbids trusting unverified text. An advisor review found the gap: a page with an invisible paragraph and one visible line was a WARNING before this rule. |
| D21 | **Repairs and truncation (P1).** A repaired document, or one without `%%EOF` in its last 2048 bytes, is recorded at document level. Each of its pages is stamped with the same WARNING, so no page of a repaired file can be `OK`. The file is kept, not rejected. | MuPDF repairs broken files silently. Per-page gates must see the problem, and a repaired file can still hold most of the document. |
| D22 | **Reading unit and raw text (P1).** Text lines are the ordering unit. A span starts a new line when its horizontal gap to the previous span is more than `line_gap_em` font sizes, in either direction. Consecutive lines that share a PyMuPDF block, a column and a band form one block. The native PDF order is never used. | PyMuPDF put the lines of two columns on one baseline in one block (seen on a synthetic page). Ordering whole PyMuPDF blocks then mixed the columns. |
| D23 | **Encryption (P1).** A file that needs a password is rejected (`encrypted_requires_password`). A file that opens without one is read, including one with an owner-only restriction on printing. | The owner's document may be restricted yet readable. Decryption is out of scope. |
| D24 | **OCR (P1).** Tesseract runs only on `SCANNED` pages, in `ocr_mode = "auto"` and only when the binary is on PATH. It is called through an argument list with no shell. Its text is `OCR_TEXT` and unverified. The tests use a stub that checks the argument list. The real binary is not installed (B2). | SPEC §3A allows an OCR fallback. Its output is not trusted (SPEC §1). |
| D25 | **Tables (P1).** Table detection uses only pdfplumber's `lines` strategy. A ruled table makes its page a WARNING, and its cell text is read in column order until P2 rebuilds the rows. Borderless tables are not detected. | On a synthetic two-column page, the `text` strategy reported a false table. A borderless table is a known gap. |
| D26 | **Classification thresholds (P1).** Every threshold in `config/default.toml` is a documented heuristic for flagging a page. None is an acceptance threshold, and none is calibrated on a real document (B1). P9b calibrates them on the development split only. | SPEC §9 forbids arbitrary thresholds. The values are config, recorded, and reviewed later. |
| D27 | **Public QA corpus (2026-11-04, owner request).** Three public documents are kept in `data/corpus/public/` for QA and regression checks: NIST SP 800-30r1 (95 pages), NIST SP 800-37r1 (102 pages) and arXiv 2506.12594 (95 pages). The PDFs are git-ignored by `*.pdf` (D7). `manifest.json` (source URL, SHA-256, size, pages, checks) and `data/corpus/README.md` are tracked. Page count was used to choose the set; the owner then said it does not matter for this corpus. None of these documents stands in for the owner's PDF (B1). | The owner asked for public, safe PDFs of about 100 pages for QA, kept in the project. The licence of the arXiv paper was not checked, so the PDFs stay local. |
| D28 | **Provenance of multi-span units (P2).** A unit's `source_spans` are half-open offsets into the page's `raw_text`, and its `raw_text` is the newline join of the spans. Lines whose raw gap is whitespace only share one span, so a paragraph that crosses P1 blocks is one verbatim slice. Only table cells and rows can have several spans (non-adjacent lines). A `table_row` unit is `derived`: its spans point at real text, its `index_text` is generated, and P6 must never quote the generated text. | The first version joined lines with `\n` across P1's `\n\n` block separators, so its 'quotations' were not on the page, and its check could not fail. Found in review and fixed in the P2 fixup. A table cell is not always one contiguous slice, so cells keep several spans. |
| D29 | **Unverified pages get block units only (P2).** A page whose status is not OK or WARNING has no sections, headings or tables. Each of its text blocks becomes one `page_text` unit, with `extraction_quality = unverified`. The page gets a `page_unstructured` issue. | SPEC §1 forbids trusting unverified text, so no structure is inferred from it. |
| D30 | **Structure thresholds in their own file (P2).** The `[structure]` section is in `config/structure.toml`. `config/default.toml` and the P1 tests are unchanged. Every threshold is a documented, uncalibrated heuristic (D26). Two were set from the corpus: `paragraph_gap_factor = 1.0` and the 0.5 pt size grid. | The P1 loader rejects unknown keys by appending to the file, so a second section there would couple the two configurations. |
| D31 | **P1 reading order is not repaired in P2.** P1 misplaces some short lines (NIST SP 800-37r1, page 20), and P2 keeps P1's order. Paragraphs that start with a lowercase letter are a proxy for a split paragraph: 151 of 1246 on arXiv (63 pages), 41 of 772 on NIST SP 800-30r1 (23 pages), and 108 of 912 on NIST SP 800-37r1 (25 pages). Those pages stay `warning`, but `warning` also covers pages in order, because `reading_order_uncertain` is set on 87, 94 and 101 pages. The repair is a clustering redesign, so it needs an owner decision (Q11). P6 depends on it. | The advisor asked for a P1 fix only where it distorts P2's input. This one does, but the repair changes P1's clustering contract, so P2 records it rather than patching it. The owner can overrule this. |
| D32 | **Storage schema revised before P3 code (ARCHITECTURE §6).** The first draft could not hold P2's output. One `location_id` per unit cannot name the spans of a table row; the bounding box is per unit; `table_row` units have no `table_cells` record, so their table fields need columns; sections need `heading_id` and an order; pages need status and hash; structure issues, page and document versions and both configuration hashes need homes. The schema is now built from the P1 and P2 models, with `PRAGMA user_version = 1`. | P2 requires one `source_locations` row per span (§11). A structure read back must equal the one written, so every field needs a column. The contract changed before the code, as the phase workflow requires. |
| D33 | **Exact phrase check (P3, ARCHITECTURE §12).** FTS5 candidates are checked on the verbatim text of each span: case-insensitive (folded one character at a time, so the length is kept), diacritic-sensitive, whitespace and no-break spaces unified, a match must lie inside one span, and word boundaries apply on both sides, with numeric boundaries (`3.5` does not match `3.5.2`, `13.5` or `3 5`). Pinned limits, each with a test: a CJK phrase inside a run of letters is not found; `İ` is not folded to `i`; a minus sign does not block a number (the P6 value check reads the sign). | On SQLite 3.49.1, FTS5's unicode61 tokenizer ignores punctuation and folds diacritics. A probe matched `3.5` to `3 5` and `3 . 5`, and `cafe` to `café`. Case folding follows FTS5 and what users expect. It is a default that the owner can tighten (for example `US` against `us`) without a schema change. |
| D34 | **Store writes (P3).** A document is written in one `BEGIN IMMEDIATE` transaction, after its records pass the write rules (hashes, spans, references, table-cell mirror). A rewrite replaces that document's rows, and a failure rolls back to the previous content. Only body-retrieval units enter `evidence_fts`. Derived table rows are indexed and stay marked `derived`. | A failed or inconsistent write must never leave a half-indexed document. Header and footer units are excluded from retrieval by the flag set in P2. |
| D35 | **Retrieval errors (P3).** `find_phrase` returns `EvidenceUnit`s in `(pdf_page, ordinal)` order, with verbatim spans. A phrase with no letter or digit raises `QueryError`, and an unknown document raises `StorageError`. Neither returns an empty list. | An empty query or a mistyped document ID must not look like "no evidence" (SPEC §9 requires abstentions to be explained). |

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

- **Status:** complete-with-limitations; **superseded by D17**. P0-CLEAN removed its artifacts on 2026-11-04. The record below is history.
- **Revision (D17, 2026-11-04):** the GPU layer and the two embedding and reranking models, with the download and validation scripts that serve them, are outside V1. P0-CLEAN removed them on 2026-11-04. The results below stay as history. The classification of what was installed and downloaded follows the table in this section.
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
  - Tests: `tests/unit/test_p0env_device.py` (20), `tests/unit/test_p0env_manifests.py` (5), `tests/integration/test_p0env_gpu.py` (3), `tests/integration/test_p0env_models.py` (4), `tests/integration/test_p0env_nlp.py` (2), `tests/integration/test_p0env_device_negative.py` (3, added in commit `c5d3f61`: the no-usable-CUDA branch with a real torch install). `tests/conftest.py` skips `requires_cuda` and `requires_models` tests with a stated reason. Both markers are registered in `pyproject.toml`.
  - Files: `requirements-gpu.txt`, `constraints-gpu.txt`, `requirements-experimental.txt`, `requirements-validated.txt` (full lock, 82 packages), `.env.example`, `models/README.md`, `models/manifests/*.json`, `docs/SETUP.md`. Updated: the header of `requirements.txt` (the stale "not included on purpose" text is removed), `docs/ARCHITECTURE.md` §7 and §9, and `README.md`.
- **Interfaces exposed:** `app.common.device.{ENV_VAR, DeviceConfigError, DeviceUnavailableError, CudaProbe, probe_cuda, resolve_device, gpu_report, cuda_matmul_smoke_test}`; `app.common.models.{sha256_file, git_blob_sha1, load_manifest, non_generative_problems, verify_manifest, smoke_test_embedder, smoke_test_reranker}`.
- **Exit criteria:** `pytest -q` (full suite, including `tests/unit/test_p0env_*.py` and `tests/integration/test_p0env_*.py`), and `scripts/validate_environment.py`, `scripts/validate_gpu.py` and `scripts/validate_models.py` each exit 0.
- **Result (recorded from runs):**
  - Project venv, full suite: `44 passed in 9.42s`, 0 skipped.
  - Clean baseline venv (`requirements.txt` only, no torch): `34 passed, 10 skipped in 0.38s`. The skips are the 3 GPU tests, the 3 negative-path tests and 2 CUDA model tests (no PyTorch), and 2 NLP tests (no spaCy or NLTK).
  - Fresh venv rebuilt from `requirements-validated.txt` (commit `f901558`, before the negative-path tests were added): `41 passed in 13.89s`. Its freeze matches the lock exactly (82 packages), and the three validators each exit 0.
  - `validate_environment.py`: `RESULT: baseline valid`. `validate_gpu.py`: `RESULT: GPU validated`. `validate_models.py`: `RESULT: all model checks passed`.
  - Fresh clone of `origin/main` at `c5d3f61`, `docs/SETUP.md` §3 run as written: the baseline step gives `33 passed, 11 skipped`, and the git-ignore test runs and passes in the clone. After all steps, `pytest -q` gives `44 passed in 11.10s`, and each validator exits 0.
  - No-usable-CUDA branch with real torch (`CUDA_VISIBLE_DEVICES=-1`): `VERITASQA_DEVICE=cuda` raises `DeviceUnavailableError`, naming the torch version and CUDA build, `requirements-gpu.txt`, and the `auto` or `cpu` fallback. `auto` and `cpu` resolve to `cpu`, and `bogus` raises `DeviceConfigError`.
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

**Classification under D17 (measured 2026-11-04, read-only).** One dependency closure over the retained pins gives each of the 83 installed distributions exactly one bucket. Sizes are the sums of the installed files listed in each package's metadata. The project venv is 3.7 GB on disk.

| Bucket | Distributions | Installed size | Status under D17 |
| --- | --- | --- | --- |
| 1. Necessary: PyMuPDF 1.26.6, pdfplumber 0.11.10, pydantic 2.14.2, pytest 9.2.0, and 16 transitive packages | 20 | 170.7 MB | Necessary. Retained in V1. |
| 2a. Optional, shared by TF-IDF and NLP: numpy, joblib, cloudpickle | 3 | 56.2 MB | Optional (Q6). Needed only if the TF-IDF baseline is kept. |
| 2b. Optional, TF-IDF only: scikit-learn, scipy, threadpoolctl, narwhals | 4 | 182.7 MB | Optional. Benchmark-only experimental baseline (P9a). |
| 2c. Optional, NLP only: spaCy, NLTK, and 36 dependencies (among them Jinja2, MarkupSafe, setuptools, requests) | 38 | 171.7 MB | Optional, pending Q6. Recommended for removal. |
| 3. rapidfuzz 3.14.6 | 1 | 6.8 MB | Owner decision (Q6). Recommended for removal. |
| 4. Removed by directive: torch 2.14.1+cu130 (its CUDA libraries are inside the package), sentence-transformers, transformers, tokenizers, safetensors, huggingface-hub, hf-xet, httpx2, httpcore2, truststore, PyYAML, sympy, networkx, mpmath, filelock and fsspec (needed only by the removed layers) | 16 | 3,311.4 MB | Unnecessary under V1. Removed in P0-CLEAN. |
| 5. Tooling: pip 26.3 | 1 | 11.9 MB | Keep. Installer tooling, not a project dependency. |
| Total | 83 | 3,911.4 MB | |

No `nvidia-*` package is installed. The CUDA runtime files (cudart, cublas, cudnn, cufft, curand and nvrtc DLLs) are inside `torch/lib`. The buckets follow from the pins as they are today. Removing spaCy and NLTK alone frees 171.7 MB. Removing TF-IDF alone frees 182.7 MB, because numpy, joblib and cloudpickle stay for spaCy. Removing both frees 410.6 MB.

**Downloads and caches (measured 2026-11-04, read-only).**

| Item | Location | Size | V1 status | Proposed action (P0-CLEAN, needs Q7) |
| --- | --- | --- | --- | --- |
| all-MiniLM-L6-v2 (embedding encoder) | `models/embeddings/` | 88 MB | Unnecessary (embedding model, D17) | Remove |
| ms-marco-MiniLM-L6-v2 (cross-encoder) | `models/rerankers/` | 88 MB | Unnecessary (reranker, D17) | Remove |
| NLTK `punkt_tab` (with its archive) | `models/nltk_data/` | 15 MB | Optional, tied to Q6. This project does not verify its digests | Remove with NLTK; otherwise keep |
| Download cache | `models/.hf-home/` | 56 KB | Unnecessary | Remove |
| Model manifests (tracked in git) | `models/manifests/` | 8 KB | Unnecessary | Remove. Git history keeps them |
| Pip download cache (shared) | `C:\Users\devdu\AppData\Local\pip\cache` (`http-v2` 18 GB, `wheels` 19 MB) | 18 GB | Not project-owned. It held 17 GB before P0-ENV installed anything | Out of scope unless the owner asks (Q7) |
| Shared Hugging Face cache (user-level `HF_HOME`) | `E:\Personal\AI-Models\huggingface` | 9.7 GB | Not written by this project. Neither chosen model is in it | Out of scope |
| Project venv | `VeritasQA/` (git-ignored) | 3.7 GB | Replaced by the V1 venv | Rebuild, then delete the old one (P0-CLEAN step 1) |

- **Limitations:**
  - Both models are validated for download, digest, non-generative architecture, loading and inference. Neither is benchmarked. Neither may enter the pipeline before P9a shows a gain over the BM25 baseline (SPEC §4, §9).
  - The GPU is a laptop RTX 5090 with 24,463 MiB. All measurements were taken on this device.
  - GPU memory is shared with an Ollama `llama-server` (PID 31904). At the same moment, `nvidia-smi` reported 5,768 MiB free and `torch.cuda.mem_get_info()` reported 23,119 MiB. The cause was not established. Every test allocation is under 0.5 GB, so the results do not depend on the choice.
  - Not tested: training, mixed precision, multiple GPUs, and a second CUDA build for comparison.
  - The NLTK resource is not checked against digests by this project.
  - No Tesseract and no GPU OCR library were installed. B2 is unchanged.
  - The optional groups are not used by any pipeline module, so their behaviour in the pipeline is unvalidated.
- **Reproducibility:** `docs/SETUP.md` §3 and §6. The baseline was rebuilt from scratch in a clean venv. The whole validated environment, including the GPU and experimental groups, was rebuilt from scratch from `requirements-validated.txt`. `docs/SETUP.md` §3 was also run as written in a fresh clone of `origin/main`.

### P0-REV — V1 revision: deterministic, LLM-free, embedding-free (D17)

- **Status:** complete (documentation, inventory and verification). The cleanup, P0-CLEAN, followed after the owner decided Q6 and Q7 (D19).
- **Trigger:** the owner's change of plans of 2026-11-04 (D17). It asks for the architecture documentation, the dependency plan and the Phase 0 checklist to be updated first. It rules out Phase 1 work, and it rules out uninstalls and deletions until the inventory is reported.
- **SPEC pointers:** §1 (constraints), §4 (retrieval), §13 (recommended technologies), §14 (phases), §16 (definition of done, item 11).
- **Done:**
  - `docs/ARCHITECTURE.md`: §1 non-goals; new §1A (precedence, determinism target, retained components mapped to phases, removed items, import target); §2 note on the historical modules; §4 controlled synonym and stemming rules, and the status of TF-IDF; §5 expansion policy; §7 dependency plan (baseline, optional, removed); §8 risks; §9 setup.
  - `docs/SETUP.md`: the V1 setup comes first, the P0-ENV sections are marked historical, and the V1 re-verification is recorded in §9.
  - `README.md`, `models/README.md`, and the headers of `requirements.txt`, `requirements-experimental.txt`, `requirements-gpu.txt`, `constraints-gpu.txt`, `requirements-validated.txt` and `.env.example`. `requirements-experimental.txt` no longer lists `sentence-transformers` or `huggingface-hub`, and no longer needs the torch constraint. The GPU, constraint and lock files carry a SUPERSEDED banner. Their pins are unchanged, because the lock is regenerated, not hand-edited.
  - `docs/SPEC.md`: the body is unchanged. The repository-written header notes the V1 precedence (D18).
  - This file: status overview, Q5 (closed), Q6 to Q8, D12 to D16 marked superseded in part, D17 and D18, the P0-ENV classification, P4 and P9a scope, and DoD 11.
  - Inventory: all 83 installed distributions are classified from one dependency closure (P0-ENV, "Classification under D17"). Sizes are measured. Models, caches and the project venv were measured read-only. Nothing was uninstalled or deleted.
  - The FTS5 `porter` tokenizer was checked in the project SQLite (3.49.1). The check shows that `run` matches `running` only with the porter tokenizer. This settles the stemming design for P4.
- **Result (recorded from runs on 2026-11-04):**
  - Project venv, full suite (`pytest -q`): before the documentation change, `44 passed in 10.62s`; after it, `44 passed in 10.19s`.
  - `scripts/validate_environment.py` in the project venv: `RESULT: baseline valid`, exit 0.
  - Fresh V1 venv built from `requirements.txt` only, in the session scratchpad (outside the repository), Python 3.12.10: install exit 0; `pip check`: No broken requirements found; `pytest -q`: `34 passed, 10 skipped in 0.31s`; torch not installed; `pip freeze --exclude pip`: 20 packages, which is the baseline closure; venv size 137 MB on disk.
  - The skips match the P0-ENV clean-venv run (34 passed, 10 skipped). They come from the missing torch, spaCy, NLTK and model files, not from failing tests.
- **Checklist (Phase 0, revised):**
  - [x] Architecture document revised.
  - [x] Dependency plan revised and classified from one closure.
  - [x] Installed packages inventoried (83 distributions) and classified.
  - [x] Downloaded models, caches and the project venv inventoried, read-only.
  - [x] Existing test suite re-run after the documentation change (result above).
  - [x] V1 baseline re-verified in a fresh venv built from `requirements.txt` only (result above).
  - [x] Q6 decided by the owner (D19): spaCy, NLTK, `punkt_tab` and rapidfuzz removed; scikit-learn kept as an optional group.
  - [x] Q7 decided by the owner (D19): the cleanup was approved.
  - [ ] Q8 decided by the owner (SPEC wording).
  - [ ] Q9 decided by the owner (synonym rules and acceptance; must precede P4).
  - [x] P0-CLEAN executed after approval (2026-11-04).
  - [x] P1 complete (2026-11-04), verified on synthetic PDFs. The real-document check is blocked (B1).
- **Limitations:**
  - The historical code is still present and still imports torch lazily (`app/common/device.py`, `app/common/models.py`). The project venv still holds torch and both models. "V1 imports no torch" was the target until P0-CLEAN, which met it on 2026-11-04.
  - SPEC §4 and §13 still describe the superseded options. D18 governs V1 until the owner decides Q8.
  - The pins did not change, so the earlier clean-venv validations (P0 and P0-ENV) still hold. The re-verification above confirms that for the current file.

### P0-CLEAN — owner-approved cleanup (complete, 2026-11-04)

- **Status:** complete
- **Decisions:** the owner answered Q6 and Q7 on 2026-11-04 (D19). spaCy, NLTK with `punkt_tab`, and rapidfuzz are removed from the V1 plan. numpy and scikit-learn stay as an optional, benchmark-only group. The cleanup was approved as proposed.
- **Branch:** `phase/p0-clean`, fast-forward merged into `main` (commit message starting `P0-CLEAN:`)
- **SPEC pointers:** §1 (constraints), §4 (optional components), §13 (dependencies), §15 (behaviour), §16 DoD 11
- **Done:**
  - Pre-delete checks: no process was running from the old venv; `models/` had no reparse points; the old venv's `pyvenv.cfg` was present.
  - A scratch venv under the session scratchpad was built from the base Python 3.12.10 interpreter, in two stages. Stage 1: `requirements.txt` only, which installs 20 packages and no NumPy. Stage 2: plus `requirements-experimental.txt`. The lock was written from stage 2's `pip freeze --exclude pip`.
  - After those checks passed, the old project venv (`VeritasQA/`, 3.7 GB) and the ignored folders `models/embeddings/`, `models/rerankers/`, `models/.hf-home/` and `models/nltk_data/` were deleted. The project venv was then rebuilt at `E:\Personal\VeritasQA\VeritasQA` from the lock. It now measures 377 MB.
  - Removed with `git rm`: `app/common/device.py`, `app/common/models.py`, `scripts/download_models.py`, `scripts/validate_gpu.py`, `scripts/validate_models.py`, `tests/conftest.py` (it held only NLTK, CUDA and model logic), the six `test_p0env_*` test files, `requirements-gpu.txt`, `constraints-gpu.txt`, `.env.example`, and the two model manifests.
  - Changed: `scripts/validate_environment.py` (baseline only); `pyproject.toml` (the `requires_cuda` and `requires_models` markers removed); `requirements.txt` (header); `requirements-experimental.txt` (numpy and scikit-learn only); `requirements-validated.txt` (regenerated, not hand-edited); `.gitignore` (the manifest and `.env.example` re-includes removed, the other guard rules kept); `models/README.md`; `docs/SETUP.md` (rewritten for V1 only); `README.md`; `docs/ARCHITECTURE.md` §1A, §2, §7, §8 and §9.
  - Added `tests/unit/test_p0_dependencies.py` (9 tests). They check the denied names in every requirement file and in `pyproject.toml`; that the baseline excludes the optional group; that the lock carries every declared pin at the same version; that an AST scan of every module under `app/` finds no denied import, including imports inside functions; that importing every `app` module in a subprocess loads no denied module; and that the scanner itself finds known imports.
- **Interfaces exposed:** none new. `app.common.errors`, `app.common.files` and `app.storage.fts5` are unchanged.
- **Exit criteria:** `pytest -q` in the new V1 venv; `pip check`; the lock equals the venv's freeze; `scripts/validate_environment.py` reports baseline valid; the deny-list tests pass.
- **Result (recorded from runs, 2026-11-04):**
  - Scratch venv, stage 1 (`requirements.txt` only): `pip check`: No broken requirements found. Baseline suite (`tests/unit/test_p0_foundation.py`): `7 passed in 0.03s`, 0 skipped. The deny-list file was excluded at this stage, because the old lock still existed. `validate_environment.py`: `RESULT: baseline valid`, exit 0.
  - Scratch venv, stage 2 (plus `requirements-experimental.txt`): `pip check`: No broken requirements found. Full suite: `16 passed in 0.13s`. The lock was written from this freeze, with 27 pins.
  - Project venv at `E:\Personal\VeritasQA\VeritasQA`, rebuilt from `requirements-validated.txt`: `pip check`: No broken requirements found. Freeze identical to the lock (sorted, comments removed). `pytest -q -rs`: `16 passed in 0.10s`, 0 skipped. `validate_environment.py`: `RESULT: baseline valid`, exit 0.
  - Fresh clone of `origin/main` at `6fa490a`, in a new directory outside the repository, with SETUP §3 run as written, using the base Python 3.12.10 interpreter in place of `py -3.12`. Baseline only: `pip check` clean; `pytest -q -rs`: `16 passed`, 0 skipped; `validate_environment.py`: `RESULT: baseline valid`. Then `requirements-validated.txt` in the same venv: `pip check` clean; freeze identical to the lock; `pytest -q -rs`: `16 passed`, 0 skipped; `RESULT: baseline valid`. The clone stayed clean.
  - Suite size: 44 tests before, 16 now. The 37 removed tests covered only the removed device, model, NLP and manifest code. The 9 new tests cover the deny-list rule. The drop is not a regression.
- **Limitations:**
  - The git-ignore test for model weights was removed with its manifests. The `.gitignore` rules remain as a guard, but no test checks them now.
  - The deny-list test cannot see imports built at run time (for example `importlib.import_module` with a computed name). It checks requirement files, `pyproject.toml`, static imports under `app/`, and the modules loaded by importing the package.
  - The lock is the freeze of one machine (Windows 11, CPython 3.12.10). Another platform needs its own lock.
  - `pip` is excluded from the lock by design. The shared pip cache (18 GB) and the shared Hugging Face cache (9.7 GB) were not touched (Q7). Ollama was not touched.
  - Q8 and Q9 are still open, and Q4 (PyMuPDF licence) is still open.

### P1 — PDF ingestion, extraction and page-level quality validation

- **Status:** complete on synthetic PDFs (2026-11-04). The real-document check is blocked (B1). The real Tesseract check is blocked (B2).
- **Branch:** `phase/p1-ingestion`, fast-forward merged into `main` (commit message starting `P1:`)
- **Contracts:** `docs/ARCHITECTURE.md` §10 (written before the code, as the workflow requires).
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
- **Done:**
  - `config/default.toml` (`[ingestion]`), loaded by `app/ingestion/config.py` with Pydantic and `extra="forbid"`. Each threshold is documented.
  - `app/ingestion/validate.py`: file checks, the SHA-256 and `document_id`. `app/ingestion/layout.py`: reading order and repeated headers and footers (pure). `app/ingestion/quality.py`: page classification (pure). `app/ingestion/extract.py`: scans every page, orders the lines, classifies, runs OCR when available. `app/ingestion/render.py`: PNG renders and the ink measure. `app/ingestion/ocr.py`: the tesseract adapter (argument list, no shell). `app/ingestion/report.py`: writes the report, the page texts and the renders.
  - Tests: `tests/unit/test_p1_*.py` and `tests/integration/test_p1_*.py`. Every PDF is generated at test time (`tests/fixtures/synthetic_pdfs.py`, labelled synthetic). The OCR stub is `tests/fixtures/fake_tesseract.py`.
- **Interfaces exposed:** `app.ingestion.validate_pdf(path, config) -> PdfFileInfo`; `app.ingestion.extract_document(path, *, config=None, out_root=None, ocr_command=None) -> ExtractedDocument`; `app.ingestion.render_page_png(path, pdf_page, dpi, out_path)`; `app.ingestion.ocr_page(...)` and `app.ingestion.tesseract_available()`; `app.ingestion.load_ingestion_config(path=None)`. `classify_page` lives in `app.ingestion.quality`.
- **Outputs (per document, under `out_root/<document_id>/`):** `extraction_report.json`, `pages/pNNNN.txt` (the immutable raw text of each page), `renders/pNNNN.png` (non-OK pages only).
- **Result (recorded from runs, 2026-11-04):**
  - Project venv, exit criteria `pytest -q tests/unit/test_p1_*.py tests/integration/test_p1_*.py`: `122 passed, 1 skipped in 8.32s`. The skip is `requires_tesseract` (tesseract is not on PATH).
  - Project venv, full suite `pytest -q`: `138 passed, 1 skipped in 8.59s`. `pip check`: No broken requirements found.
  - Fresh venv built from `requirements.txt` only (in the session scratchpad, CPython 3.12.10): `pip check` clean; the freeze is the 20-package baseline with no NumPy; `scripts/validate_environment.py`: `RESULT: baseline valid`.
  - Fresh clone of `phase/p1-ingestion` (it held only committed files, and its status was clean), run with the `requirements.txt`-only venv: exit criteria `122 passed, 1 skipped in 8.53s`; full suite `138 passed, 1 skipped in 8.78s`; `scripts/validate_environment.py`: `RESULT: baseline valid`.
  - Timing on a synthetic 100-page two-column document: 4.0 s, including the report. All 100 pages were `OK`.
  - Problems the tests found and that were fixed before this result: PyMuPDF placed two columns in one block (D22); the built-in Helvetica font substitutes `—` and `€` (so the Unicode fixture uses the embedded `china-s` font); `china-s` drops some Latin letters on insertion (so the fixture uses only letters it keeps). The last two were fixture errors, not extractor errors. Their evidence is in the glyph trace. An advisor review found that a page with an invisible paragraph and one visible line was a WARNING, which could ground an answer. It is now SUSPICIOUS (D20), and the test `test_no_page_with_invisible_text_is_ever_verified` covers every fixture with invisible text.
- **Limitations:**
  - No real document (B1). Every threshold is uncalibrated, and the precision of no flag has been measured. The synthetic results describe the pipeline, not the owner's document.
  - Real tesseract was not run (B2). The OCR path is tested with a stub that checks the argument list, the failure exit and the empty-output case.
  - Reading order is a heuristic, tested on synthetic layouts only. Ruled-table cells are read in column order, and borderless tables are not detected (`lines` strategy only, D25).
  - Invisible-text detection depends on PyMuPDF's render-mode trace. A visible text layer over an image is also `SCANNED_TEXT_LAYER` (unverified), which is conservative and may cost coverage.
  - The garbled and private-use checks are not calibrated. Symbol-font bullets may count as private-use characters, so the limit is loose.
  - Image coverage sums the image areas and caps the sum at 1. Overlapping images can therefore over-count.
  - OCR text has page-level coordinates only. Rotated pages are flagged, and their coordinates are not normalized.
  - A repaired or truncated document makes every page a WARNING (D21), so none of its pages can be `OK` until the owner decides otherwise.
  - Text that is invisible by colour (for example white text, render mode 0) is not detected. Only render modes 3 and 7 are.
  - Footnotes are not identified in P1. SPEC §3A lists them, and the plan gives them to P2. DoD 2 therefore does not yet cover them.
  - Header and footer roles come from a text key with digits collapsed. A numeric row that repeats at a page edge can be tagged as a header. The role is a flag, and P2 must not delete the unit.
  - Q4 (the PyMuPDF licence) is still open. This phase uses the library as pinned.
  - Corpus evidence (P2, 2026-11-04): on the three public documents, P1 flags reading order as uncertain on 87 of 95, 94 of 95 and 101 of 102 pages. On NIST SP 800-37r1, page 20, a bullet's last line is read after the next bullet's marker. P2 keeps P1's order (D31).
- **Handoff to P2:**
  - Load a written report with `app.ingestion.load_outputs(report_path)`, which checks each page-text file against `raw_text_sha256`. The JSON alone does not validate, because it omits `raw_text`.
  - A line with `hidden_chars > 0` is unverified (D20). Only `OK` pages are `verified`. A `WARNING` page carries `warning` quality, and every other status is `unverified`.
  - `block_no` is the PyMuPDF block a line came from. One PyMuPDF block can yield several blocks, so use `reading_index` and `raw_start`/`raw_end` for identity.
  - Table cells are read in column order (D25). P2 rebuilds the rows from the pdfplumber cells.

### P2 — Structure reconstruction, provenance and evidence segmentation

- **Status:** complete-with-limitations (2026-11-04). The synthetic fixtures and the three public documents pass every property check. Heading, paragraph and table quality on real documents is unmeasured (B1, D26).
- **Branch:** `phase/p2-structure`, fast-forward merged into `main` (commit message starting `P2:`).
- **Contracts:** `docs/ARCHITECTURE.md` §11, written before the code and corrected against the corpus probes. The signature is `build_structure(extracted, pdf_path)`: the PDF is needed only for table geometry, and its SHA-256 must match the report.
- **SPEC pointers:** §3B (structure and segmentation), §2.3 (provenance), §6 (answer context), §16 DoD 3
- **Scope:**
  - **Normalization (reversible):** `app/common/text.py` `normalize_with_map(raw) -> NormalizedText(text, index_to_raw)`. NFKC per character, with each output character mapped back to its raw offset. Unify quote and dash variants, map NBSP to space, remove soft hyphens, and dehyphenate line-end breaks in index text only. Test ligatures, NBSP, soft hyphen, curly quotes, combining marks, CJK, Arabic (RTL).
  - **Headings:** body font size from the character-weighted size mode; headings are larger or bold short lines; the hierarchy comes from the ranks of the heading sizes. Produce `sections` with parent links.
  - **Units:** paragraphs (wrapped lines merged, offsets kept into `raw_text`), list items attached to their intro (`parent_id`), captions (`Table n` / `Figure n`) attached to their table, footnotes from the bottom band, and header/footer units kept but excluded from body retrieval by a flag.
  - **Tables:** pdfplumber cells with a header row. Each cell becomes a unit carrying `row_header`, `col_header`, `caption`, `table_id`, `row_index` and `col_index`. Each row also gets a unit whose text states the header-value pairs, so a number is never indexed without its row and column.
  - **Neighbours:** `prev_id`, `next_id`, `section_id`, `parent_id`, bounding box, `content_type`, inherited `extraction_quality`.
- **Interfaces to expose:** `app.common.text.normalize_with_map`; `app.document_structure.build_structure(extracted) -> DocumentStructure(sections, units, table_cells)`; `EvidenceUnit` (Pydantic) with the fields in ARCHITECTURE §3.
- **Exit criteria:** `pytest -q tests/unit/test_p2_*.py tests/integration/test_p2_*.py`
- **Done:**
  - `app/common/text.py`: `normalize_with_map` (a raw range for every index character; NFKC over each base character with its combining marks; quote and dash unification; soft hyphen and invisible marks; line-end dehyphenation, index text only), and `normalize_text`.
  - `app/document_structure/`: `config.py` (`config/structure.toml`, Pydantic, `extra="forbid"`), `models.py` (`EvidenceUnit`, `Section`, `TableCell`, `StructureIssue`, `DocumentStructure` with `config_sha256`), `tables.py` (pdfplumber boxes and line-to-cell assignment), `segment.py` (classification, paragraph and list grouping, heading levels), `build.py` (`build_structure`, the emitter, sections, table units, neighbours), `errors.py`.
  - Tests: `tests/unit/test_p2_normalization.py`, `test_p2_config.py`, `test_p2_tables.py`; `tests/integration/test_p2_structure.py` (synthetic fixture in `tests/fixtures/structure_pdfs.py`); `tests/integration/test_p2_corpus.py` (marker `public_corpus`, which skips when a PDF is absent); property checks shared through `tests/fixtures/structure_checks.py`.
- **Result (recorded from runs, 2026-11-04):**
  - Exit criteria `pytest -q tests/unit/test_p2_*.py tests/integration/test_p2_*.py`: `51 passed in 35.86s`. The six corpus tests take about 35 s of that.
  - Full suite `pytest -q -rs`: `189 passed, 1 skipped in 44.19s`. The skip is `requires_tesseract`, as before. `pip check`: No broken requirements found.
  - Public corpus (not the owner's PDF; property checks only): single-span units are verbatim slices of their page text, with 0 failures. Multi-span units exist only as table units: arXiv 21 cells and 10 rows; NIST SP 800-30r1 13 cells and 238 rows; NIST SP 800-37r1 3 cells and 137 rows. Uncovered non-space text: 0. Overlapping non-derived units: 0.
    - arXiv 2506.12594: 1457 units, 98 sections, 22 table cells, 0 issues.
    - NIST SP 800-30r1: 3770 units, 71 sections, 1766 table cells; issues `page_unstructured` 1, `table_header_uncertain` 2.
    - NIST SP 800-37r1: 2774 units, 71 sections, 966 table cells; issues `page_unstructured` 1, `table_geometry_mismatch` 8.
  - Problems found by the tests and probes, and fixed before this result: the short-line rule compared a line with its own one-line block, not with its column (D30); paragraphs could not continue across P1's one-line blocks (474 of 496 body blocks on arXiv pages 1 to 10 hold one line); the paragraph-gap factor was 0.4, but normal leading on arXiv is about 0.5 of the line height, so it is now 1.0; one stray line in a larger font had been pushing every later heading level down, so a size now needs two heading lines; footnotes now need a marker. The first quotation check could not fail: multi-block paragraphs were stored as a newline join that is not on the page. Found in review; fixed in the P2 fixup, so they are now verbatim single spans.
- **Limitations:**
  - Quality on real documents is unmeasured. No gold structure exists (B3), and every threshold is an uncalibrated heuristic (D26).
  - Headings are font-based. On the arXiv document, figure labels at 10 to 13 pt qualify as heading levels and push the section headings down to level 5 or 6. The cover-page title lines of NIST SP 800-37r1 become separate sections.
  - Reading order is P1's (D31). P1 misplaces some short lines (NIST SP 800-37r1, page 20). 151, 41 and 108 paragraphs (arXiv, NIST SP 800-30r1, NIST SP 800-37r1) start with a lowercase letter, a sign of a split paragraph. Reading order is flagged uncertain on 87 of 95, 94 of 95 and 101 of 102 pages, so most units are `warning`, not `verified`. P6 needs the repair first (Q11).
  - Tables: pdfplumber boxes that disagree with the text are skipped. On NIST SP 800-37r1, eight tables on pages 81 to 85 (RMF figures) were skipped. The first row of every table is taken as its header row.
  - Running heads: P1 finds no repeating running head on the arXiv document, so the author line stays body text. The furniture rule covers digit-only lines only.
  - No corpus document has page labels, so the printed-page case of D4 has no real example yet.
  - A footnote without a marker stays a paragraph.
- **Handoff to P3:** `build_structure(extracted, pdf_path)` returns a `DocumentStructure`, which records `config_sha256`. Quotations come from `raw_text` through `source_spans`. Only table units have several spans, so write one `source_locations` row per span. `index_text` and `heading_text` are for FTS5. Never quote a `derived` row. Header and footer units have `body_retrieval = false`. Each table cell carries `table_id`, `row_index`, `col_index`, `row_header`, `col_header` and `caption` for the `table_cells` table (ARCHITECTURE §6).

### P3 — SQLite schema, FTS5 and exact phrase retrieval

- **Status:** complete-with-limitations (2026-11-04). The exact-phrase path is verified on synthetic documents and, as property checks, on the three public documents. Retrieval quality on real documents is unmeasured (B1, B3).
- **Branch:** `phase/p3-storage-retrieval`, fast-forward merged into `main` (commit message starting `P3:`).
- **Contracts:** `docs/ARCHITECTURE.md` §6 (revised before the code, D32) and §12.
- **SPEC pointers:** §3C (storage), §4 (exact phrase, escaping), §12 (escaping and SQL safety), §16 DoD 4
- **Scope:**
  - `app/storage/schema.py` creates the tables in ARCHITECTURE §6 (`documents`, `pages`, `sections`, `source_locations`, `evidence_units`, `table_cells`, `evidence_fts`, `evaluations`). Checks FTS5 at open (`ensure_fts5_available`).
  - `app/storage/repository.py` writes and reads with parameterized SQL only, scoped by `document_id`.
  - Multi-span units (table cells and rows) need one `source_locations` row per span (ARCHITECTURE §11).
  - `app/retrieval/query.py` builds FTS5 queries from tokens quoted with a fixed pattern. The query is kept reversibly beside the source text.
  - `app/retrieval/phrase.py` runs an FTS5 phrase query for candidates, then applies a deterministic check on normalized text (`3.5` must not match `3 5` or `3 . 5` by accident).
- **Interfaces to expose:** `app.storage.Store` (open, check FTS5, write document, query); `app.retrieval.phrase.find_phrase(store, document_id, phrase) -> list[EvidenceUnit]`.
- **Test plan:** FTS5-syntax characters (`"`, `*`, `:`, `^`, `-`, `NEAR(`, `AND`, `OR`, parentheses) and SQL-injection strings must be harmless. Phrase vs. adjacency. Unicode queries. Two documents in one database must not leak results across `document_id`.
- **Exit criteria:** `pytest -q tests/unit/test_p3_*.py tests/integration/test_p3_*.py`
- **Done:**
  - `app/common/errors.py`: `StorageIntegrityError(StorageError)` and `QueryError(VeritasQAError)`.
  - `app/storage/schema.py` (the §6 DDL, `PRAGMA user_version = 1`, refusal of another version and of a database with foreign tables), `integrity.py` (the write rules), `repository.py` (parameterized reads and writes; FTS rows for body units only), `store.py` (`Store`, the write transaction, `DocumentRecord`), `__init__.py`.
  - `app/retrieval/query.py` (`build_phrase_query`, `PhraseQuery`, `MATCH_COLUMN`), `phrase.py` (`span_matches`, `fold_case`, `find_phrase`), `__init__.py`.
  - Tests: `tests/unit/test_p3_schema.py`, `test_p3_repository.py`, `test_p3_query.py`, `test_p3_phrase_check.py`, `test_p3_phrase_search.py`; `tests/integration/test_p3_retrieval.py` (synthetic PDFs through P1, P2 and the store) and `test_p3_corpus.py` (the three public documents in one store, marker `public_corpus`).
  - Shared helpers: `tests/fixtures/store_records.py` (hand-built P1 and P2 records, labelled synthetic) and `tests/fixtures/store_checks.py` (`brute_force_phrase`, `row_counts`).
- **Result (recorded from runs, 2026-11-04):**
  - Exit criteria `pytest -q tests/unit/test_p3_*.py tests/integration/test_p3_*.py`: `233 passed in 64.92s`, with no skips (the public corpus files were present).
  - Full suite `pytest -q -rs`: `422 passed, 1 skipped in 110.09s`. The skip is `requires_tesseract`, as before. Baseline before P3: `189 passed, 1 skipped`.
  - `pip check`: No broken requirements found.
  - First run of the P3 unit tests: 209 passed, 1 failed. The failure was the test's own expected text (`schema version 99`; the message reads `the database schema is version 99`). The test was corrected and the message kept.
  - Mutation check (scratch probe, not kept as a test): with the exact check disabled, `3.5` also returns `13.5`, `3.55` and `3.5.2`, and `risk assessment` also returns `Risk. assessment`. With the check on, both are excluded, and the phrase-search tests assert those exclusions.
  - Round trip: `load_structure(write(x)) == x` holds on the synthetic structure, on a second document with identical text, and on the three public documents (95, 95 and 102 pages), which passed the P2 property checks after the store round trip.
  - Problems found and fixed before this result:
    1. The first schema draft could not hold P2's output (D32). Found by review against P2's models; ARCHITECTURE §6 was corrected before the code.
    2. FTS5 over-matches punctuation, spacing and diacritics (probe on SQLite 3.49.1; D33), so the exact check is required.
    3. Raw user text passed to MATCH is a syntax error (`'); DROP TABLE …` raised `fts5: syntax error`), so every token is quoted and placed behind one column filter (ARCHITECTURE §12).
    4. The first boundary rule skipped the neighbour check at a punctuation edge, so `-5` would have matched inside `3-5`. Found by review before the tests ran; the rule now checks the neighbouring character whatever the phrase's edge is.
- **Limitations:**
  - Retrieval quality on the owner's document is unmeasured (B1, B3). The public corpus gives property checks only; no gold answers exist.
  - CJK text without spaces forms long token runs. `文字` does not find `文字の認識`, but a phrase equal to a whole run is found (pinned in `test_p3_phrase_check.py`). Substring retrieval for CJK is not planned for V1.
  - Diacritics are significant in the exact check, so `cafe` does not match `café`. Case is not significant, so `US` matches `us`. P5 and P6 decide entity and value matches.
  - `İ` is not folded to `i` (pinned). A minus sign does not block a number match: `3.5` matches `-3.5`, and the P6 value check reads the sign.
  - The FTS index uses the default unicode61 tokenizer. No stemming, synonyms or ranking (P4).
  - A phrase copied from a table row's generated `index_text`, with its ` | ` or ` = ` glue, is not found, by design.
  - `created_at` is the only column that differs between runs of the same input.
- **Handoff to P4:**
  - `find_phrase` is the exact-match path. P4 adds BM25 ordering as `ORDER BY bm25(evidence_fts, w_index, w_heading)` in a query that also filters `document_id`. The FTS table is shared, so every query must carry that filter. Keep the raw score internal and never show it as a probability.
  - All documents share one FTS5 table, so BM25 IDF is computed over the whole store, and adding a document changes the scores of the others. P4 must choose per-document or shared statistics, and record the choice against the determinism target (ARCHITECTURE §1A).
  - FTS hits are never evidence by themselves. P4 candidates are checked in P6 against raw text (ARCHITECTURE §5). Expansion-only matches stay candidates (D17, Q9).
  - Derived rows (`derived = true`) must never be quoted.
  - P4 is blocked on Q9.

### P4 — BM25 retrieval and candidate ranking

- **Status:** not started
- **SPEC pointers:** §4 (BM25, heading-aware, numeric preservation, K, duplicates, expansion), §9 (do not expose scores as probability), §12 (BM25 ranking direction), §16 DoD 4
- **Scope:**
  - `app/retrieval/bm25.py`: `ORDER BY bm25(evidence_fts, w_text, w_heading) ASC LIMIT K` with rank assigned from position. The raw BM25 value is stored separately and never shown as a probability.
  - Heading-aware weights, read from config.
  - `app/retrieval/terms.py`: extract numeric, date and identifier terms (for example `3.5`, `10%`, `2024-01-01`, `ABC-123`) so verification can check them later.
  - Duplicate removal by hash of normalized text. Expansion adds neighbours and section siblings as context only and never replaces evidence.
  - RRF is not implemented. It is added only if a benchmark shows a gain (P9).
  - **Controlled synonym and stemming rules (D17).** Recall only. A versioned data file (planned `config/retrieval_rules.toml`) lists each rule with an ID, a version, positive examples, counter-examples and a reviewer note. Expansion is query-time and one-way; the index is not rewritten. Each expansion is recorded in the retrieval trace with its rule ID. Expanded matches only add candidates. The entity, value, negation and condition checks (P6) run on raw text and cannot be satisfied by an expansion alone. This is the default. Whether reviewed rules may count toward acceptance is owner decision Q9.
  - **No index stemming in V1.** The FTS5 `porter` tokenizer exists in this SQLite build (3.49.1), and with it `run` matches `running`. The tokenizer is fixed per FTS table, so it needs a second table and cannot be switched per query. It is not used unless the P4 regression set shows a need.
  - **Tests.** Each rule has positive and negative cases, and a false-match regression set covers each rule (`tests/regression/`). Tests assert that each expansion is logged with its rule ID, and that an expansion-only match does not pass a P6 entity, value, negation or condition check.
- **Interfaces to expose:** `app.retrieval.bm25.search(store, document_id, query, k, weights) -> list[RetrievalCandidate]`.
- **Exit criteria:** `pytest -q tests/unit/test_p4_*.py tests/integration/test_p4_*.py`
- **Result:** not run yet
- **Limitations (expected):** lexical only. Synonyms are limited to the reviewed rules. Paraphrases are missed by design, and abstention covers the misses.

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
- **Prerequisite:** the P1 reading-order repair (Q11, D31), or the owner's decision to accept P1's order. The context checks read `prev_id` and `next_id`.
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
- **Scope:** a sweep harness over K, neighbour window and heading weight, run on the dev split only. It reports results and never writes calibrated values into the policy file. RRF and TF-IDF may run as experimental baselines on the dev split. TF-IDF is sparse lexical weighting, benchmark-only, and outside the acceptance path. Embeddings and cross-encoder reranking are not part of V1 and are not benchmarked (D17).
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
| 2 | Extraction issues detected and exposed | P1 complete on synthetic PDFs; the real-document check is blocked (B1) |
| 3 | Evidence provenance accurate | P2 complete: the provenance invariants hold on the synthetic fixtures and on the three public documents. Accuracy on the owner's document is blocked (B1). |
| 4 | BM25 and exact phrase retrieval reliable | P3 done (exact phrase, complete-with-limitations); BM25 is P4 |
| 5 | Supported answer types use extractive selection | P5 |
| 6 | Exact quotations and page citations verifiable | P6 |
| 7 | Unsupported questions trigger abstention | P7 |
| 8 | Conflicts exposed, not resolved silently | P7 |
| 9 | Evaluation metrics from manually verified data | blocked (B3); harness P8a |
| 10 | Regression tests for discovered failures | P8a (framework), grows as failures are found |
| 11 | Critical functionality runs without a generative LLM, an embedding model or PyTorch (D17) | Done in P0-CLEAN. `tests/unit/test_p0_dependencies.py` enforces the deny-list in the requirement files and `pyproject.toml`, in the imports under `app/`, and in the modules loaded by importing the package. The project venv holds no PyTorch and no model. |
| 12 | Documentation explains limitations and reproducible setup | P10 (README), ARCHITECTURE §8–9 |
