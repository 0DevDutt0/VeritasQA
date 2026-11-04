# VeritasQA — Progress and Handoff

> **Read this file first in every new session.** It is the source of truth for what is done, what is blocked and what comes next. The requirements are in [`docs/SPEC.md`](docs/SPEC.md); design decisions are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## How to resume (after `/clear`)

Say **"continue"**. Then work through the first phase below whose status is `in progress` or `not started`, and follow the per-phase workflow. A phase whose status is `blocked` on an owner decision stops the run: report the open decision and wait. Do not start a later phase.

**Current resume point (2026-11-04, after P6):** P0-REV, P0-CLEAN and P1 to P6 are complete. **P7 is next** (conflict detection, decision engine and abstention). On "continue", start P7, follow the per-phase workflow and stop at its phase boundary. Q4 (the PyMuPDF licence), Q8, Q10, Q11 and Q12 are still open. Q11 and Q12 were put to the owner at the end of P6, in plain words, with their recommendations, and neither is decided (D60). Neither blocks P7. P6 marks every result that depends on reading order, or on a flagged page, as UNRESOLVED (D62). So the owner's answer to Q11 changes how many pages count as verified, and the code does not change. Q3 (install Tesseract) decides whether the OCR path is ever run for real (B2).

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
| P4 | BM25 retrieval and candidate ranking | complete-with-limitations (recall measured on the three public documents only; no synonym rule is approved, D43) | `pytest -q tests/unit/test_p4_*.py tests/integration/test_p4_*.py` |
| P5 | Question analysis and extractive selection | complete-with-limitations (no stemming or synonyms in the subject check; who and where give passages only; public-corpus counts are a property check, not a measurement, B1) | `pytest -q tests/unit/test_p5_*.py tests/integration/test_p5_*.py` |
| P6 | Evidence verification and citations | complete-with-limitations (verified on synthetic documents; on the public documents, property counts only; PASS is rare because most pages are flagged, D62; support on the owner's document is blocked, B1) | `pytest -q tests/unit/test_p6_*.py tests/integration/test_p6_*.py` |
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
- **Q9. Synonym rules and acceptance.** The default stays conservative. An expansion can widen the candidate set, but it cannot satisfy the entity, value, negation or condition checks, which run on raw text (`docs/ARCHITECTURE.md` §4 and §5). Should reviewed rules ever count toward acceptance? A yes needs a per-rule flag such as `verification_eligible` (default off), a regression set that shows no false acceptances, and a decision recorded here. Recommendation: keep the default off. Answer this before P4 is built. **Status: closed on 2026-11-04. The owner answered "no" (D38).**
- **Q10. Public QA corpus (D27).** Should the three public PDFs in `data/corpus/public/` be committed, or kept local? The two NIST documents are US federal works. The licence of the arXiv paper (2506.12594) was not checked. Recommendation: keep the PDFs local (D7) and track only the manifest and the README.
- **Q11. P1 reading-order repair (D31).** Should the repair of P1's column clustering come before P6? P6's context, negation and qualifier checks read `prev_id` and `next_id`, which follow P1's order. Options: (a) repair P1 before P6; (b) accept P1's order for P6 and mark every context-dependent verdict `UNRESOLVED` on a page with `reading_order_uncertain`. Recommendation: (a). It need not block P3 or P4. **Owner's answer (2026-11-04): store for the next phase.** Not decided. P6 put it to the owner at its end (D60). It does not block P7.
- **Q12. Derived table rows (P2 table index text).** P2 leaves the values of headerless columns out of a row's generated `index_text`. It also joins adjacent cells that share one raw line into one span (D28), so a phrase that crosses a cell boundary is not in the row's index. Across the public corpus, 417 of 1,488 derived rows (28.0%) have at least one span that their index does not state (571 spans). 204 of those spans equal one cell's text, and all 204 are found through their cell. 330 are runs of whole cells: each constituent cell (735) is found through its own unit, but the cross-cell phrase returns the row in 0 of 330 cases. 37 are parts of one cell (34, all found through that cell) or partial merges (3, not classified further). The recall test excludes 16 of 481 windows, all derived rows (ARCHITECTURE §12). Should P2 be reopened as a fixup, to list every value in the row text and to split spans at cell boundaries? Recommendation: yes, before P6 uses derived rows as evidence. P3 is not blocked either way. **Owner's answer (2026-11-04): store for the next phase.** Not decided. P6 put it to the owner at its end (D60). It does not block P7.

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
| D33 | **Exact phrase check (P3, ARCHITECTURE §12).** FTS5 candidates are checked on the verbatim text of each span: case-insensitive (folded one character at a time, so the length is kept), diacritic-sensitive, whitespace and no-break spaces unified, a match must lie inside one span, and word boundaries apply on both sides, with numeric boundaries (`3.5` does not match `3.5.2`, `13.5` or `3 5`). Pinned limits, each with a test: a CJK phrase inside a run of letters is not found; `İ` is not folded to `i`; a minus sign does not block a number (the P6 value check reads the sign); a private-use glyph glued to a word hides the word. | On SQLite 3.49.1, FTS5's unicode61 tokenizer ignores punctuation and folds diacritics. A probe matched `3.5` to `3 5` and `3 . 5`, and `cafe` to `café`. Case folding follows FTS5 and what users expect, and only where the index folds the character (D37). It is a default that the owner can tighten (for example `US` against `us`) without a schema change. |
| D34 | **Store writes (P3).** A document is written in one `BEGIN IMMEDIATE` transaction, after its records pass the write rules (hashes, spans, references, table-cell mirror). A rewrite replaces that document's rows, and a failure rolls back to the previous content. Only body-retrieval units enter `evidence_fts`. Derived table rows are indexed and stay marked `derived`. | A failed or inconsistent write must never leave a half-indexed document. Header and footer units are excluded from retrieval by the flag set in P2. |
| D35 | **Retrieval errors (P3).** `find_phrase` returns `EvidenceUnit`s in `(pdf_page, ordinal)` order, with verbatim spans. A phrase with no letter or digit raises `QueryError`, and an unknown document raises `StorageError`. Neither returns an empty list. | An empty query or a mistyped document ID must not look like "no evidence" (SPEC §9 requires abstentions to be explained). |
| D36 | **Whole-phrase FTS5 query and a superset boundary (P3; this amends the scope wording of P3).** The scope planned tokens quoted with a fixed pattern. The code quotes the normalized phrase as one FTS5 string, with every double quote doubled, behind the column filter. The exact check's word-boundary set includes private-use characters and marks, so it contains every character unicode61 keeps inside a token. | A per-token query missed a phrase that held a private-use character or a folded combining mark: a scratch measurement returned no hit for `ab`, U+E000, `cd`, though the text contains that phrase. One FTS5 string is tokenized by the index's own tokenizer, so the two sides cannot disagree about token boundaries. |
| D37 | **Case folding is calibrated to the index (P3 fixup 2).** The exact check folds a character only where the FTS5 index folds it. The set is measured once per process on a private in-memory database of the same SQLite build (`index_foldable_characters`). On SQLite 3.49.1, 416 of 1,432 cased single characters in planes 0–1 are excluded, mainly Cherokee, Old Hungarian, Georgian Mtavruli, Osage, Vithkuqi, Adlam, Warang Citi and Medefaidrin. For those characters the phrase search is case-sensitive. | A cross-script sweep found pairs that Python folds and FTS5 does not. The exact check then accepted pairs the candidate step could not return (Georgian Mkhedruli against Mtavruli, and Cherokee, in both directions). Aligning the exact check with the index keeps the superset property for every character, and it needs no hand-kept table. |
| D38 | **Owner answer on synonym rules (Q9), 2026-11-04: no.** A reviewed synonym or stemming rule never counts toward acceptance in V1. Rules only add candidates (recall). A candidate that a rule reached and no original query word reached is `expansion_only`, and no check may accept it as support. No per-rule `verification_eligible` flag is built. A later "yes" needs a new owner decision, a per-rule flag, a false-acceptance regression set, and a recorded decision. | The owner's answer to the question the file asked before P4 was built. The recommendation was "no". Under "no", the rule mechanism stays recall-only, and the acceptance path needs no change. |
| D39 | **BM25 statistics are per document (P4).** `bm25()` runs on a temporary FTS5 table that holds only the body units of the requested document. It has the same columns and tokenizer as `evidence_fts`, and it is rebuilt on each search (about 6 ms for 3,000 units on this machine). | §1A requires the same PDF, question and configuration to give the same response. Shared statistics let a second document change the first one's IDF, scores and ranking. The stored `evidence_fts` table is unchanged. |
| D40 | **`search()` returns a `RetrievalResult` (P4).** It holds the candidates and a trace: the normalized words, the query's numbers and identifiers, each applied rule with its ID and version, the rule-set fingerprint, the counts and the truncation. The planned `-> list[RetrievalCandidate]` is changed to match (ARCHITECTURE §13). | Each expansion must be logged with its rule ID (D17, D38). The trace needs a place to travel with the candidates. |
| D41 | **Slots (P4).** Original-word hits are cut to `k` after duplicate removal. Expansion-only hits follow and are cut to `expansion_k`. An expansion never takes an original hit's place. | A rule can add candidates, but it cannot push out a unit that the user's own words reached. Tested with `k = 1`. |
| D42 | **Context (P4).** A candidate's context is up to `context_window` body units before and after it, in reading order, plus the headings of its section and of its parent section. Context is never a candidate. No separate list of all section siblings is attached. | SPEC §4 asks for parent-section and neighbouring context. The plan's "section siblings" is read as the in-section neighbours inside the window, because a whole section on every candidate would be too large. The owner can overrule this reading. |
| D43 | **No rule is approved in V1 (P4).** `config/retrieval_rules.toml` lists none, so the default expansion adds nothing. The mechanism is tested with fixture rules in `tests/fixtures/`. A rule is added only after the owner has reviewed its examples and reviewer note. Each candidate also lists the query's numbers, dates and identifiers that appear exactly in its raw text (`exact_terms`). | The owner has not reviewed any rule, so adding one is the owner's decision. The exact-term list is information for P6, and ranking does not use it. |
| D44 | **Corpus recall is measured and reported, not gated (P4).** The public-corpus test counts how many sampled windows return their own unit within K = 50 and within K = 10, and it does not fail on a miss. K, the window size and any stop-word handling are for P9a to decide on the development split. | The owner's rule is that recall is measured and never assumed. A threshold chosen after seeing the result would be tuning to pass, so none is set. The one miss is analysed in the P4 section. |
| D45 | **One selection result per question component (P5).** `select_candidates(analysis, retrieved, units)` takes the retrieval result of each component and the loaded units. It returns one `ComponentSelection` per component, with a status and plain-text reasons. The flat list in the earlier plan is replaced (ARCHITECTURE §14). | SPEC §5: "Never silently omit unanswered components." An unsupported, ambiguous or empty component must be reported. A candidate's `via` decides its status, so retrieval results are needed too. |
| D46 | **Retrieval candidates are kept by reference (P5).** An `AnswerCandidate` holds the P4 `RetrievalCandidate` unchanged. Scores, `via`, rule IDs, duplicates and context are not copied or recomputed. A component whose candidates come only from reviewed rules has status `expansion_only`, and it is never reported as having original-word support. | The P4 handoff and D38: an expansion-only candidate is never evidence. One object avoids two sources of truth. |
| D47 | **Answer spans only where a rule decides them (P5).** An answer span is given only for a number with a unit, a percentage, a currency amount, a date or period, and a permission or prohibition marker. Every other type returns its sentence, or its passage for conditions, with `no_answer_span`. No name or place extraction is attempted. | SPEC §6: without a rule-supported span, return the passage "without claiming it is a verified answer". A name or place extractor without a tagger would be a guess (no spaCy in V1, D19). |
| D48 | **Table cells are passage-only; derived rows are not quoted (P5).** A table cell is quoted whole, with the flag `table_cell` and no answer span, even for a value. A derived table row is never quoted and is listed as dropped (`derived_row`). | A bare number in a cell has no link to its row's subject, and the row question (Q12) is open. P4's handoff says P5 must not quote a derived row. |
| D49 | **A quote is verbatim or it is not built (P5).** A quote is a slice of one source span, so `page_text[page_start:page_end] == quote`. A sentence that would join two spans is dropped (`crosses_source_span`), not joined with a newline. | P2 (D28) joins non-adjacent lines with a newline, so a joined quote would not appear on the page. |
| D50 | **Sentence splitting is conservative (P5).** A full stop after an abbreviation or an initial does not end a sentence, unless the next word opens a sentence (`The`, `This`, and so on). A line break is whitespace. | Not splitting is the safe direction: a longer quote can be checked, while a wrong split can cut the sentence that carries the value or the negation. Tested on `U.S. Department` (no split) and `in the U.S. The next` (split). |
| D51 | **The value grammar excludes identifiers and footnote marks (P5).** `3.5.2`, `1,2,3`, `ABC-123`, `800-53`, `FISMA,1` and `agencies.2` are not values. A number and its unit may be separated by a line break. | Each of these would otherwise be read as a number. `3.5.2` against `3.5`, and `FISMA,1` read as `1 the`, are traps found in the public corpus output. |
| D52 | **Question types, compound splits and ambiguity (P5).** The types are the SPEC §5 list plus `unsupported`. A compound question is split at `?`, and at `and`, `or` or `;` when the next words open a new question. A comparison is split into subjects only when they are explicit. Anything that cannot be searched is `ambiguous` or `unsupported`, with a reason. | SPEC §5: unsupported, ambiguous or complex structures "must return evidence for inspection or abstain". Without a parser, arbitrary comparison subjects are not guessed. |
| D53 | **Target and attribute terms (P5).** Target terms are the content words that are not function words, question words or attribute words. All target terms must appear in one sentence, using the exact check (D33). Attribute words come from a controlled list, together with light predicate verbs (`apply`, `need`, `require`, `include`, `happen` and similar). Neither kind is required in the sentence. | Requiring the subject in the sentence is the first step of the entity check (SPEC §7, check 4). Without a tagger, a list of attribute words is the honest way to separate subject from property. |
| D54 | **Retrieval per component; the glue stays outside the package (P5).** A component is searched with its `retrieval_query`. The caller runs `search()` and `Store.load_unit`. The package has no store-aware orchestrator. | The decision phase owns `answer()` (P7). The integration tests do the glue, so there is no second path to the store yet. |
| D55 | **Replacement characters are flagged, not dropped (P5).** A quote containing U+FFFD keeps its candidate and gets the flag `replacement_character`. | Verification (P6) decides what a damaged quote may support. Dropping it here would hide the damage from the record. |
| D56 | **A pronoun in a later clause takes the earlier subject, or the clause is ambiguous (P5).** A later clause with a referential pronoun (`it`, `they`, `them`, `its`, `their`, `he`, `she`, `him`, `her`) takes the target terms of the clause before it. Its own words are predicates, so they do not replace that subject. If the earlier clause has no target terms, the later clause is `ambiguous`. A pronoun in a single question (`is it permitted`) is not affected. | Without this rule, `when is it due` would search for the word `due` alone, which names no subject. An unresolved reference must stop the search, not widen it. |
| D57 | **Candidates carry the citation (P5).** Each `AnswerCandidate` holds the `pdf_page` and the `section_id` of its unit. | SPEC §6 requires page and section references for every passage. The corpus provenance check found that the page was missing. Reading it through the retrieval object would tie the citation to scoring. |
| D58 | **No stemming and no synonyms in the subject check (P5).** A subject word must match exactly. `loans` does not match `loan`, and `applies` does not match `apply`. | D17 and D38 keep synonym rules reviewed and out of acceptance, and a stemming rule would be a new owner decision. The cost is recall: a word that differs from the text's form is missed, and no wrong passage is added. |
| D59 | **Count nouns and label words (P5).** A number counts as a quantity through a count noun only when the noun is a target word of the question, is lower case as written, follows a number that is not dotted, and does not open a line. A number directly after a label word (`Section`, `Table`, `Step`, `Page`, and similar) is an identifier, not a value. | A heading such as `3.2 Risk`, read with the count noun `risk`, would give the wrong answer span `3.2 Risk`. Found in review before the fix, and tested by a regression case and by unit tests for each guard. |
| D60 | **Reading order (Q11) and table rows (Q12) are stored for the next phase (2026-11-04).** The owner's answer to both was "store for the next phase". That is a deferral, not a decision, so both stay open and undecided. The next phase puts both to the owner first, with their recommendations (reading-order repair before the context checks; a fixup of the table index text before table rows are used as evidence). Until they are settled, any result that relies on reading order or on table rows is `UNRESOLVED`. | Neither question blocks the start of the next phase, because the checks that depend on them can return `UNRESOLVED` without guessing. Deciding them now, without the owner's choice, would decide a P1 or P2 change that the owner has not approved. |
| D61 | **Verifier contract (P6).** `verify(candidate, analysis, store, document_id)` returns a `VerificationReport`. The candidate is a claim. Every check re-reads the stored page and unit and recomputes what it needs (values, markers, polarity, word matches). None of the candidate's `values`, `attribute_hits` or `negated` is copied. The verdict is FAIL when a required check fails, PASS when every required check passes (NOT_APPLICABLE is allowed only for the attribute and value checks), and UNRESOLVED otherwise. Inputs that do not line up raise `VerificationError`. Architecture §15. | SPEC §7: exact quotation proves source integrity, not support, and an ambiguous relation stays unresolved. A copied claim could be wrong without any check noticing. |
| D62 | **Flagged pages (P6; Q11 applied conservatively).** Source quality passes only on a `verified` page. A `warning` or `unverified` page is UNRESOLVED, and its stored issue codes are the reason. `Store.page_warning_codes` reads them from `pages.warnings_json` (read only; no schema change). The stored record does not say which warning applies to a page, so neighbours are read only on a verified page. Vocabulary v1 (reviewed by reading): strong qualifiers (`except`, `unless`, `only if`, `provided that`, `does not apply`, `do not apply`, `however`, `subject to`), negation words, and hedges (`might`, `could`, `possibly`, `probably`, `perhaps`, `unclear`, `uncertain`, `appears to`, `seems to`, `is likely`, `are likely`). | The owner's Q11 choice changes how many pages can be verified, and the code is the same either way. A reading order that is wrong can put a qualifier in the wrong sentence, so a flagged page cannot be called clean. |
| D63 | **Value occurrence (P6).** A question value (number, percentage, date or identifier, read by P4's term rule) occurs in a passage only with its boundaries. No letter, digit, underscore, `.`, `,` or `/` may come before it. After it, no letter, digit or underscore, and no `.`, `,` or `/` followed by a letter or digit. A minus sign attached in front (not itself after a letter, digit or `)`) makes the occurrence negative. A value that occurs only negatively is FAIL. A value that does not occur is UNRESOLVED. | P3's phrase check does not read the sign, and it accepts `3.5` inside `-3.5`. The value check must read the sign. Tests pin `3.5` against `-3.5`, `3.5.2`, `1,2,3`, `13.5`, `15` inside `5`, and `10-15`. |
| D64 | **Flags, expansion-only and derived rows (P6).** Each blocking P5 flag gives UNRESOLVED on `candidate_flags`: `no_answer_span`, `multiple_values`, `multiple_markers`, `table_cell`, `list_marker`, `comparison_subject` and `replacement_character`. An unknown flag does too. A candidate reached only by a reviewed rule FAILs the entity, value, negation and condition checks. A derived table row FAILs the location check. | SPEC §7 and the P4 and P5 handoffs. The owner's rule (D38) is that an expansion is never support. |
| D65 | **Required checks per type (P6).** Every type requires the same ordered list: quotation, location, answer span, entity, attribute, value, context, negation, condition, source quality and candidate flags. Passage-only types (what, who, where, which, conditions and comparison) have no span, so their answer-span check is UNRESOLVED and they can never PASS. Only when, how many and whether can PASS, and only with exactly one value or marker at its stored offsets. | SPEC §6: without a rule-supported span, a passage is returned without a verified answer. SPEC §9: ANSWERED needs supported extraction. The per-type table is in architecture §15. |
| D66 | **Conflict screening is pending (P6).** Check 10 is listed in every report with status `PENDING`. It is not part of the verdict. A PASS is candidate-level: the decision step (P7) still runs conflict screening and the acceptance policy. | SPEC §8 compares passages across the whole document, which is a decision-step task. Keeping it out of the verdict stops a PASS from being read as the final answer. |
| D67 | **Property words are matched exactly (P6; a consequence of D58).** A property word of the question, such as `permitted` in "Is staff permitted to…?", must occur in the passage, by P3's exact check. A passage that says only `may` is UNRESOLVED. No synonym is used. | D38 and D58: synonyms are not approved. The effect on permission questions is real and is reported in the P6 limitations. A reviewed synonym rule would change it, but it needs a new owner decision (D38) before it could count as support. |

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
  - `app/retrieval/query.py` (`build_phrase_query`, `PhraseQuery` with the raw-range mapping, `MATCH_COLUMN`; the whole normalized phrase is one quoted FTS5 string, D36), `phrase.py` (`span_matches`, `fold_case`, `find_phrase`), `__init__.py`.
  - Tests: `tests/unit/test_p3_schema.py`, `test_p3_repository.py`, `test_p3_query.py`, `test_p3_phrase_check.py`, `test_p3_phrase_search.py`, `test_p3_tokenizer_agreement.py` (24 characters across the Unicode categories that matter to unicode61, each checked for self-retrieval and brute-force agreement), `test_p3_case_folding.py` (15 cased pairs across scripts, both directions, and the alignment of the exact check with the index); `tests/integration/test_p3_retrieval.py` (synthetic PDFs through P1, P2 and the store) and `test_p3_corpus.py` (the three public documents in one store, marker `public_corpus`, including the recall test on real windows).
  - Shared helpers: `tests/fixtures/store_records.py` (hand-built P1 and P2 records, labelled synthetic) and `tests/fixtures/store_checks.py` (`brute_force_phrase`, `row_counts`).
- **Result (recorded from runs, 2026-11-04):**
  - Exit criteria `pytest -q tests/unit/test_p3_*.py tests/integration/test_p3_*.py`: `321 passed in 70.07s` on the final code, with no skips (the public corpus files were present). The first P3 commit recorded `233 passed`, the first fixup `272`, and this fixup adds the case-folding tests and the lone-surrogate test.
  - Full suite `pytest -q -rs`: `510 passed, 1 skipped in 113.65s` on the final code (the first P3 commit recorded `422`, the first fixup `461`). The skip is `requires_tesseract`, as before. Baseline before P3: `189 passed, 1 skipped`, and 189 + 321 = 510.
  - Tokenizer panel: 24 characters from the Unicode categories that matter to unicode61, each with a self-retrieval check and brute-force agreement on three sub-phrases, all pass. The old per-token query returned no hit for `ab`, U+E000, `cd` (scratch measurement), so the panel would have caught it.
  - Recall on the public corpus: 465 windows, cut from the normalized text of 174 sampled units across eight body content types (heading 48, paragraph 58, footnote 50, list item 65, caption 63, table cell 60, table row 78, page text 43), each found its own unit. 16 windows of derived rows were excluded because their generated index does not state them (Q12).
  - `pip check`: No broken requirements found.
  - First run of the P3 unit tests: 209 passed, 1 failed. The failure was the test's own expected text (`schema version 99`; the message reads `the database schema is version 99`). The test was corrected and the message kept.
  - Mutation check (scratch probe, not kept as a test): with the exact check disabled, `3.5` also returns `13.5`, `3.55` and `3.5.2`, and `risk assessment` also returns `Risk. assessment`. With the check on, both are excluded, and the phrase-search tests assert those exclusions.
  - Round trip: `load_structure(write(x)) == x` holds on the synthetic structure, on a second document with identical text, and on the three public documents (95, 95 and 102 pages), which passed the P2 property checks after the store round trip.
  - Problems found and fixed before this result:
    1. The first schema draft could not hold P2's output (D32). Found by review against P2's models; ARCHITECTURE §6 was corrected before the code.
    2. FTS5 over-matches punctuation, spacing and diacritics (probe on SQLite 3.49.1; D33), so the exact check is required.
    3. Raw user text passed to MATCH is a syntax error (`'); DROP TABLE …` raised `fts5: syntax error`), so the normalized phrase is passed as one quoted string, with its quotes doubled, behind one column filter (ARCHITECTURE §12, D36).
    4. The first boundary rule skipped the neighbour check at a punctuation edge, so `-5` would have matched inside `3-5`. Found by review before the tests ran; the rule now checks the neighbouring character whatever the phrase's edge is.
    5. A per-token query missed a phrase with a private-use character or a folded combining mark. Run once against the old construction, the tokenizer panel fails 2 of 24 characters (U+0301 and U+E000, both on the self-phrase). The whole-phrase query fixed it (D36), and the panel passes 24 of 24 on the new one.
    6. The corpus recall test first failed on a derived row whose generated index text does not state one of its values. The cause is P2's table index text (Q12), not P3. The check was then narrowed to the windows the index states, and the excluded windows are counted (16 of 481). The narrowing is disclosed here, not hidden: the full-corpus classification is in Q12 (417 of 1,488 derived rows, 28.0%).
    7. A cased-pair test, run across several scripts, found that the exact check folded pairs the index does not fold (Georgian Mtavruli, Cherokee). A sweep of planes 0 and 1 found 416 of 1,432 cased characters the index does not fold. The exact check now folds only the characters the index folds (D37), so it cannot accept a pair the candidate step cannot return.
    8. A lone surrogate in a phrase raised `UnicodeEncodeError` at bind time. It is now a `QueryError`, with a test.
- **Limitations:**
  - Retrieval quality on the owner's document is unmeasured (B1, B3). The public corpus gives property checks only; no gold answers exist.
  - CJK text without spaces forms long token runs. `文字` does not find `文字の認識`, but a phrase equal to a whole run is found (pinned in `test_p3_phrase_check.py`). Substring retrieval for CJK is not planned for V1.
  - Diacritics are significant in the exact check, so `cafe` does not match `café`. Case is not significant, so `US` matches `us`. P5 and P6 decide entity and value matches.
  - `İ` is not folded to `i` (pinned). A minus sign does not block a number match: `3.5` matches `-3.5`, and the P6 value check reads the sign.
  - The FTS index uses the default unicode61 tokenizer. No stemming, synonyms or ranking (P4).
  - A phrase copied from a table row's generated `index_text`, with its ` | ` or ` = ` glue, is not found, by design.
  - `created_at` is the only column that differs between runs of the same input.
  - **A private-use character glued to a word hides the word** (`ab`, U+E000, `cd`: `ab` does not find it). Pinned in `test_p3_phrase_check.py`. A symbol-font glyph with no space beside a word has this effect.
  - **Derived table rows are found only through the text their generated index states.** Across the public corpus, 417 of 1,488 derived rows (28.0%) have a span their index does not state. Every single-cell value is found through its cell, and every constituent cell of a merged span is too. Only the cross-cell phrase is lost (0 of 330 merged runs). The cause is P2 (Q12), and the owner decides whether to reopen it.
  - **Recall is measured on the public corpus only.** The 465 windows (174 sampled units, eight body content types) each found their own unit, and 16 more were excluded as derived-row windows the index does not state. That is recall for the windows the index states, and it is not a measurement on the owner's document (B1, B3).
  - **For characters the index does not fold, the phrase search is case-sensitive.** On SQLite 3.49.1 that is 416 of 1,432 cased single characters in planes 0 and 1 (mainly Cherokee, Old Hungarian, Georgian Mtavruli, Osage, Vithkuqi, Adlam, Warang Citi and Medefaidrin). `Ꭰ` does not find `ꭰ`. This is a recall miss, never a false acceptance (D37, tested in `test_p3_case_folding.py`).
- **Handoff to P4:**
  - `find_phrase` is the exact-match path. P4 adds BM25 ordering on a per-document index (D39, ARCHITECTURE §13). The raw score stays internal and is never shown as a probability.
  - BM25 statistics were index-wide in P3. P4 chose per-document statistics (D39), so this handoff item is closed.
  - FTS hits are never evidence by themselves. P4 candidates are checked in P6 against raw text (ARCHITECTURE §5). Expansion-only matches stay candidates (D17, Q9).
  - Derived rows (`derived = true`) must never be quoted.
  - The owner answered Q9 with "no" on 2026-11-04 (D38), so P4 is no longer blocked.
  - Q12 (P2 table index text) is open. If the owner reopens P2, remove the derived-row exclusion from `test_p3_corpus.py`, so that the recall test covers every window.

### P4 — BM25 retrieval and candidate ranking

- **Status:** complete-with-limitations (2026-11-04). The owner's answer to the synonym-rule question is D38 ("no"). **Branch:** `phase/p4-bm25-ranking`, fast-forward merged into `main`.
- **SPEC pointers:** §4 (BM25, heading-aware, numeric preservation, K, duplicates, expansion), §9 (do not expose scores as probability), §12 (BM25 ranking direction), §16 DoD 4
- **Scope:**
  - `app/retrieval/bm25.py`: `ORDER BY bm25(evidence_fts, w_text, w_heading) ASC LIMIT K` with rank assigned from position. The raw BM25 value is stored separately and never shown as a probability.
  - Heading-aware weights, read from config.
  - `app/retrieval/terms.py`: extract numeric, date and identifier terms (for example `3.5`, `10%`, `2024-01-01`, `ABC-123`) so verification can check them later.
  - Duplicate removal by hash of normalized text. Expansion adds neighbours and section siblings as context only and never replaces evidence.
  - RRF is not implemented. It is added only if a benchmark shows a gain (P9).
  - **Controlled synonym and stemming rules (D17).** Recall only. A versioned data file (planned `config/retrieval_rules.toml`) lists each rule with an ID, a version, positive examples, counter-examples and a reviewer note. Expansion is query-time and one-way; the index is not rewritten. Each expansion is recorded in the retrieval trace with its rule ID. Expanded matches only add candidates. The entity, value, negation and condition checks (P6) run on raw text and cannot be satisfied by an expansion alone. This is the default. Whether reviewed rules may count toward acceptance is owner decision Q9.
  - **No index stemming in V1.** The FTS5 `porter` tokenizer exists in this SQLite build (3.49.1), and with it `run` matches `running`. The tokenizer is fixed per FTS table, so it needs a second table and cannot be switched per query. It is not used unless the P4 regression set shows a need.
  - **Tests.** Each rule has positive and negative cases, and a false-match regression set covers each rule (`tests/regression/`). Tests assert that each expansion is logged with its rule ID, and that an expansion-only candidate is flagged (D38). The check that such a candidate fails the P6 checks moved to the P6 section, because those checks do not exist yet.
- **Interfaces to expose:** `app.retrieval.bm25.search(store, document_id, query, *, k, weights, context_window, expansion_k, rules, config) -> RetrievalResult` (D40, ARCHITECTURE §13). The parameters are keyword-only, so a sweep can override any of them.
- **Exit criteria:** `pytest -q tests/unit/test_p4_*.py tests/integration/test_p4_*.py`
- **Built:** `app/retrieval/bm25.py` (`search`, `RetrievalResult`, `RetrievalCandidate`, `QueryTrace`), `terms.py` (numbers, percentages, dates, identifiers), `rules.py` (rule loader with example checks, one-way expansion, fingerprint), `config.py` and `errors.py`; `app/storage/retrieval_reads.py` and four store methods (`document_bm25_index`, `unit_summaries`, `body_neighbours`, `section_headings`); `config/retrieval.toml` and `config/retrieval_rules.toml` (no rule approved). Tests: `tests/unit/test_p4_{terms,config,rules,bm25,dedupe,context,expansion}.py`, `tests/integration/test_p4_{retrieval,corpus}.py`, `tests/regression/test_p4_rule_false_matches.py`, with fixtures `tests/fixtures/retrieval_docs.py` and `tests/fixtures/retrieval_rules_test.toml`. Documents: ARCHITECTURE §4, §5, §12 (amended) and §13 (contract); README status.
- **Result (recorded from runs, 2026-11-04, on the final code):**
  - Exit criteria `pytest -q tests/unit/test_p4_*.py tests/integration/test_p4_*.py`: `123 passed in 116.52s`. The public PDFs were present, so the corpus tests ran.
  - Full suite `pytest -q -rs`: `641 passed, 1 skipped in 228.39s`. The skip is `requires_tesseract` (`tests/unit/test_p1_render_ocr.py:121`), as before.
  - `tests/unit/test_p0_dependencies.py`, checked separately as well: `9 passed`.
  - Public-corpus recall, a property check with no gold answers, reported and not gated (D44): 179 of 180 sampled windows return their own unit within K = 50, and 174 of 180 within K = 10. Per document: nist-sp800-30r1 60/60 and 59/60; nist-sp800-37r1 59/60 and 56/60; arxiv-2506-12594 60/60 and 59/60.
  - The one miss within K = 50 is nist-sp800-37r1, unit `p0057:u0004`, a 54-word paragraph. Its window is "the system) to the authorizing official". Two of its words are common ("the", "to"), and the unit ranks 63rd of 1,075 candidates, below shorter units that hold the rarer words "authorizing" and "official". BM25 normalizes for length, so this is the ranking working as designed. Whether K or stop words should change is for P9a to decide.
  - Scratch mutation checks, kept outside the repository as in P3: (a) with shared, index-wide statistics, the isolation test fails and the scores of the first document move by up to 2.67, while the shipped code moves them by 0.000000; (b) with the failed-build cleanup disabled, the cleanup test fails.
- **Problems found and fixed during the phase:**
  1. The first ranking fixture gave the heading-only unit an exact tie with a body unit under equal weights, so the ID tiebreak hid the heading effect. The fixture's heading-only unit now has a longer body. The ranking code was not changed.
  2. FTS5 clamps the IDF of a term that occurs in more than half the rows to 1e-6. The 11-unit sample document therefore ties. The ranking tests use a larger fixture, and `assert_idf_is_informative` checks that first.
  3. Two duplicate-removal expectations miscounted the copies: four units share one normalized text, not three. The expectation now counts from the group. The code's count of three was right.
  4. A test assumed every candidate was `verified`. The ruled-table page is a warning page (D25), so the test checks that each candidate carries the quality its unit was stored with.
  5. The corpus recall test first asserted no misses at K = 50, and the miss above failed it. The test now reports the figures without a gate, as D44 records. This changed the test design, and it is recorded here rather than hidden.
  6. A failed index build left its temporary table behind, so later searches on that store would report "already open". Any failure now drops the table, and SQLite errors are reported as `StorageError`. A test injects the failure, and the mutation check above confirms the test fails without the cleanup.
  7. The K = 10 figure is now taken from the first ten entries of the K = 50 list, since the ranking does not depend on K. The corpus test runs one search per window instead of two.
- **Limitations:**
  - Recall is measured on the three public documents only (a property check, no gold answers). The owner's document is not in `data/documents/` (B1), so no recall figure exists for it.
  - No synonym or stemming rule is approved (D43). The rule mechanism is tested with synthetic fixture rules only, so expansion adds nothing to a query until the owner reviews and approves a rule.
  - BM25 candidates are a superset of exact matches: FTS5 matches `3.5` inside `3.5.2`. Each candidate's `exact_terms` shows whether the exact form is present. P6 checks it.
  - A comma-separated list of numbers, such as `1,2,3`, is read as one term.
  - Stop words are not removed. A long question can return many candidates (1,413 original hits for one corpus window), and `k` cuts them.
  - Scores are comparable only within one document (D39).
  - No stemming: `run` does not find `running` unless a rule lists it.
  - Duplicate removal uses the normalized text only. Near-duplicates are not removed.
  - Context is the neighbouring body units and the section headings. No full section text is attached (D42).
  - Each search rebuilds the document's index (about 6 ms for 3,000 units on this machine).
  - The defaults are uncalibrated, and P9a sweeps them on the development split: `k` = 50, `expansion_k` = 10, `weight_index` = 1.0, `weight_heading` = 2.0, `context_window` = 1.
- **Handoff to P5 and P6:**
  - P5 receives `search()` results. Each candidate carries `exact_terms`, `derived`, `extraction_quality`, `via` (`expansion_only` is true for expansions), `rule_ids` and `context`. P5 must not quote a derived row, and it must not treat an `expansion_only` candidate as evidence.
  - P6 owns the check moved from P4 (D38): an `expansion_only` candidate must fail the entity, value, negation and condition checks on raw text.
  - Q11 (reading order) and Q12 (table index text) must be settled before P6 relies on context or derived rows. Neither blocks P5.

### P5 — Question analysis and extractive selection

- **Status:** complete-with-limitations (2026-11-04). **Branch:** `phase/p5-question-selection`, fast-forward merged into `main`.
- **SPEC pointers:** §5 (question processing), §6 (extractive answer selection), §12 (numeric and unit extraction, negation, entity mismatch, unsupported and compound questions)
- **Contract:** ARCHITECTURE §14. The decisions are D45 to D59.
- **Built:**
  - `app/question_processing`: `analysis.py` (`analyze`, `QuestionAnalysis`, `QuestionComponent`, `QuestionType`, `ValueIntent`), `vocabulary.py` (function, question, attribute, negation and opener words, reviewed by reading), `errors.py` (`QuestionError`). Ten question types: nine supported and `unsupported`. Compound questions split at `?`, and at `and`, `or` or `;` before a question opener. Comparisons split only at explicit subjects. A referential pronoun in a later clause takes the earlier subject (D56).
  - `app/evidence`: `values.py` (`find_values`: numbers with units, percentages, currency, dates, periods and ranges, plus count nouns taken from the question; the exclusions are in D51 and D59), `segment.py` (`sentence_spans`, with the abbreviation rule of D50), `markers.py` (`find_markers`: permission and prohibition markers with polarity, condition markers and list markers), `selection.py` (`select_candidates`, `ComponentSelection`, `AnswerCandidate`, `DroppedCandidate`, `RULE_IDS`), `errors.py` (`SelectionError`).
  - Tests: unit `tests/unit/test_p5_values.py`, `test_p5_segment.py`, `test_p5_analysis.py`, `test_p5_selection.py`; integration `tests/integration/test_p5_synthetic.py` (a stored synthetic document, checked against the stored page text) and `test_p5_corpus.py` (the public corpus: gated checks and reported counts); regression `tests/regression/test_p5_false_answers.py` (ten named cases, each with a precondition that can fail).
- **Interfaces:** `app.question_processing.analyze(question) -> QuestionAnalysis`; `app.evidence.select_candidates(analysis, retrieved, units) -> SelectionResult` (D45). The caller runs `search()` with each component's `retrieval_query` (D54), and loads each returned unit with `Store.load_unit`. The result has one `ComponentSelection` per component, so none is omitted.
- **Exit criteria:** `pytest -q tests/unit/test_p5_*.py tests/integration/test_p5_*.py`
- **Result (recorded from runs, 2026-11-04, on the final code):**
  - Exit criteria: `165 passed in 92.19s`. The regression set `tests/regression/test_p5_false_answers.py`: `10 passed in 0.27s`. The phase has 175 tests in total.
  - Full suite `pytest -q -rs`: `816 passed, 1 skipped in 321.49s`. The skip is `requires_tesseract` (`tests/unit/test_p1_render_ocr.py:121`), as before. The P4 corpus recall is unchanged: 179 of 180 windows within K = 50, and 174 of 180 within K = 10.
  - Trap mutations, kept outside the repository. Six rules were each broken once, and each break was caught by at least one test: the footnote check in the number boundary (5 failures), the abbreviation opener rule (4), the pronoun rule (4), the expansion-only status (1), the capital-letter count guard (1, after a test was added for it, because the heading test was also caught by the dotted-number guard), and the label-word guard (4). Every file was restored byte for byte. Earlier mutations also broke the offset mapping for multi-span units (1 test) and quoted derived rows (2 tests).
  - Public corpus, property checks with no gold answers. Gated checks, which pass on every generated question: each quote equals the stored page text at its offsets, no derived row is quoted, each answer span lies inside its quote, and the output is deterministic. Reported counts follow. Each question was built from a sentence's own words, so "the source sentence came back" is partly built in and is weak evidence.
    - `what`: 116 questions, 116 with candidates, 116 containing their source sentence.
    - `how many`: 3 questions, all with candidates, 1 with an answer span. The public text has very few numbers with time units, so this path is barely exercised on real text.
    - `when`: 44 questions, 42 with candidates, 42 containing their source sentence, 212 answer spans (counted per candidate).
    - `whether`: 32 questions, 26 with candidates, 25 containing their source sentence, 40 answer spans.
    - `conditions`: 31 questions, 30 with candidates, 28 containing their source sentence.
    - `which`: 58 questions, 58 with candidates, 55 containing their source sentence.
    - Replacement character: none of the three public documents contains U+FFFD (their non-letter characters are bullets, dashes and quotation marks). So the replacement-character gate ran only in the synthetic unit test, not on real text.
    - Dropped units: 1,290 derived rows and 3 crossing a join. Flags: `no_answer_span` 1,255, `list_marker` 131, `table_cell` 40, `multiple_values` 5, `multiple_markers` 4.
    - Values read in body units: 1,089 numbers, 56 dates, 15 percentages, 1 period. Full stops after an abbreviation that precede a capital letter: 121 kept and 1 split.
- **Problems found and fixed during the phase:**
  1. A number at the very start or end of a text was rejected, because an empty string tests as a member of any string. Fixed before the first test run.
  2. A verb in a question (`apply` in `how many days apply to loans`) became a required subject word, so no sentence without that verb could match. Light predicate verbs are now attribute words (D53). The regression set caught it.
  3. A pronoun in a later clause (`when is it due`) was searched on its predicate word (`due`). Now the clause takes the earlier subject, or it is ambiguous (D56).
  4. An unsupported or ambiguous component still exposed a retrieval query, so a caller could search for it by accident. Its query is now empty.
  5. Answer candidates did not carry the page number, although SPEC §6 requires it. The corpus provenance check found the gap. `pdf_page` and `section_id` are now fields of each candidate (D57).
  6. The word `share` was a property word (the proportion sense), so `share data` lost its verb. It is now a subject word.
  7. The first corpus generator produced no "how many" questions, because it sampled only forty units. It now scans every body unit for quantities, up to a cap. The generator also covers the `when`, `whether`, `conditions` and `which` types, so those run on real text too.
  8. A section heading such as `3.2 Risk`, followed by a count noun from the question, read `3.2` as a quantity in the unit `risk`, which would give a wrong answer span. Found in review before any run on real text. Fixed by D59, with regression and unit tests.
  9. A line break inside a Python string in the value grammar was written as a real newline by a shell edit, which broke the module. Caught by the parser, repaired, and the file re-checked.
- **Limitations:**
  - No stemming and no synonyms in the subject check. `loans` does not match `loan`, and `applies` does not match `apply` (D58). A miss is a loss of recall, not a false answer.
  - All subject words must appear in one sentence (D53). An answer that needs two sentences is not found.
  - `who` and `where` give passages only (D47). A name or a place is never extracted.
  - A written number (`three days`) is not a value, so it gives no `how_many` answer span.
  - Table cells are passage-only (D48). A derived row is never quoted, until Q12 is settled.
  - Only the candidates that retrieval returned are examined, so the depth `k` limits recall. The default is uncalibrated, and P9a sweeps it.
  - Only the listed question forms are read. Anything else is reported as ambiguous or unsupported and is not guessed. Comparison subjects come only from explicit wording.
  - The abbreviation list, the marker lists, the label words and the attribute-word list are uncalibrated, and they were reviewed by reading. Nothing here was tuned on a gold answer.
  - The public-corpus counts are property checks with no gold answers. They are not a measurement on the owner's document (B1, B3). On real text, the `how many` path is thin, and the replacement-character gate did not run. The synthetic tests carry both.
  - A replacement character is flagged, not repaired (D55).
  - Nothing in this phase decides support. A candidate is a passage, and only P6 and P7 decide whether it supports an answer.
- **Handoff to P6 and P7:**
  - Each `AnswerCandidate` carries `retrieval` (by reference: `via`, `expansion_only`, `rule_ids`, `derived`, `extraction_quality`, duplicates and context), `pdf_page`, `section_id`, `quote` with its page offsets, `answer_span` with its offsets when a rule gives one, `values`, `negated`, `attribute_hits` and `flags`.
  - P6 must fail every `expansion_only` candidate on the entity, value, negation and condition checks (D38). It must not treat `no_answer_span`, `multiple_values`, `multiple_markers`, `table_cell`, `list_marker`, `comparison_subject` or `replacement_character` as support. Each of these is a reason for `UNRESOLVED` at least.
  - P7 receives one `ComponentSelection` per component. A component whose status is `ambiguous`, `unsupported` or `no_candidates` is reported with its reasons, and it is never omitted (SPEC §5).
  - Q11 (reading order) and Q12 (table rows) are still open. P5 quotes no derived row, but context from P1's order is still unverified until Q11 is settled.

### P6 — Evidence verification and citations

- **Status:** complete-with-limitations (2026-11-04). Verified on labelled synthetic documents. On the three public documents the counts are property checks only, and PASS is rare, because most pages are flagged (D62). Support on the owner's document is blocked (B1). Conflict screening is pending in the decision step (D66).
- **Branch:** `phase/p6-verification`, fast-forward merged into `main` (commit message starting `P6:`).
- **Contract:** `docs/ARCHITECTURE.md` §15, written before the code (D61 to D67).
- **Built:** `app/verification` (`errors.py`, `vocabulary.py`, `report.py`, `terms.py`, `checks.py`, `verifier.py`, `__init__.py`). Store read added: `Store.page_warning_codes` and `repository.read_page_warning_codes`, which read the existing `pages.warnings_json` column (no schema change).
- **Tests:** unit `tests/unit/test_p6_vocabulary_terms.py`, `test_p6_checks.py` (one group per check), `test_p6_verifier.py` (verdict rule, required checks, input errors, pending conflict check); integration `tests/integration/test_p6_synthetic.py` (verified and flagged pages, polarity, store reads, complete reports) and `test_p6_corpus.py` (marker `public_corpus`, counts reported); regression `tests/regression/test_p6_false_acceptances.py` (one case per false acceptance, each with a precondition); fixtures `tests/fixtures/verification_docs.py`.
- **SPEC pointers:** §7 (the eleven checks, quotation integrity is not semantic support), §10 (evidence record), §12 (provenance, negation, entity mismatch), §16 DoD 6
- **Scope:**
  - `app/verification/checks.py`: one function per check (1 quotation integrity, 2 location integrity, 3 answer-span integrity, 4 entity, 5 attribute, 6 value, 7 context, 8 negation, 9 condition, 10 conflict screening (calls P7 later), 11 source quality). Each returns `PASS`, `FAIL`, `UNRESOLVED` or `NOT_APPLICABLE`, with a reason.
  - `app/verification/verifier.py`: explicit required-check lists per question type. A candidate passes only when every required check is `PASS`.
  - Context uses neighbours without changing the evidence. Exception and qualifier markers (`except`, `unless`, `only if`, `provided that`, `does not apply`, `however`) make the result `UNRESOLVED`.
  - **Moved from P4 (D38):** an `expansion_only` candidate from P4 must not pass the entity, value, negation or condition checks. The test belongs here, because those checks are written in this phase.
- **Interfaces to expose:** `app.verification.verify(candidate, analysis, store, document_id) -> VerificationReport`.
- **Exit criteria:** `pytest -q tests/unit/test_p6_*.py tests/integration/test_p6_*.py`
- **Result (recorded from runs, 2026-11-04, on the final code):**
  - Exit criteria `pytest -q tests/unit/test_p6_*.py tests/integration/test_p6_*.py`: `105 passed in 85.06s`. This includes the public corpus test, with the three PDFs present.
  - Regression `pytest -q tests/regression/test_p6_false_acceptances.py`: `16 passed in 0.36s`.
  - Full suite `pytest -q -rs`: `937 passed, 1 skipped in 410.93s (0:06:50)`. The skip is `requires_tesseract` (`tests/unit/test_p1_render_ocr.py:121`), as before. The P5 baseline was 816 passed, 1 skipped, and 816 + 121 = 937 (105 exit-criteria tests and 16 regression tests).
  - Mutation check (scratch, outside the repository, as in P4 and P5): twelve single-line breaks, one for each rule family. Each was caught by at least one test, and each file was restored byte for byte. Two breaks survived on the first run. One was a harness error: the entity break landed after the early return, so it changed nothing. The other was a real gap: a flagged last sentence whose next sentence is on a clean page. The test `test_a_flagged_page_is_not_read_for_context_even_when_its_next_unit_is_clean` now covers it.
  - Public corpus (property counts, not a measurement on the owner's document): 284 questions gave 1,517 candidates. Verdicts: 0 PASS, 0 FAIL and 1,517 UNRESOLVED. Quotation and location PASS for all 1,517, so every quote is verbatim. The candidates' pages: 39 verified, 1,474 warning, 4 unverified. Answer-type candidates: 262 (when 215, whether 44, how many 3), of which 253 have a single span. 209 are blocked only by their page's flag, which is an upper bound for a reading-order repair (the context check would still have to pass). Only 3 answer-type candidates lie on verified pages, and all three list several dates, so P5 flags them as multiple values. The corpus has no clean single-value answer on a verified page, so the zero PASS is the correct result for this corpus, not a defect. The synthetic verified-page cases cover the PASS path.
- **Problems found and fixed during the phase:**
  1. The word-boundary pattern for the qualifier and hedge lists had no group, so the boundaries attached only to the first and last phrase, and `except` matched inside `exceptional`. A unit test caught it. The pattern is now grouped (`vocabulary.py`), and a mutation check pins it.
  2. Test-side errors, not verifier errors: `fee` is a property word, not a target word, so the entity case uses `guarantee`. `permitted` is a property word, so the permission fixtures use passages that contain it (D67). P5 does not select a passage whose number is only a longer token, so the identifier and longer-number cases are checked against passages that P5 does select.
  3. The determinism test first compared a list with itself. It now re-runs the verifier on a sample of the corpus candidates.
  4. The flagged-page context gap found by the mutation check, described above.
- **Prerequisite (Q11, D31):** the verifier reads each unit's stored quality at run time, so the code is the same whichever way the owner answers Q11. The answer changes how many pages are verified. The context checks read `prev_id` and `next_id`, and those follow P1's order. The owner stored Q11 and Q12 for this phase on 2026-11-04, undecided (D60). They were put to the owner again at the end of this phase, in plain words, with recommendations. Neither blocks the next phase.
- **Limitations:**
  - PASS is rare on the public corpus: 0 of 1,517. Most candidates sit on flagged pages (the reading-order question, Q11), and the corpus has no clean single-value answer on a verified page. The owner's document will have its own figure (B1).
  - **A property word must match exactly (D67).** A question that asks "permitted" is UNRESOLVED on a passage that says only "may", because synonyms are not used (D38, D58). This is the largest recall cost found in P6.
  - Negation scope and hedges are read in the sentence only. The context check reads the two neighbours for strong qualifiers, not for negation words (`docs/ARCHITECTURE.md` §15).
  - Passage-only types (what, who, where, which, conditions and comparison) never pass in V1 (D65).
  - Conflict screening is pending (D66). A PASS is candidate-level, not a final answer.
  - The vocabulary (qualifiers, negation words, hedges, blocking flags) was reviewed by reading. It is not calibrated on any gold answer.
  - A PASS shows that the question's words, value and marker are in the passage, with the stated polarity. It does not show that the passage answers the question (SPEC §7).
- **Handoff to P7:**
  - Each candidate has one report: a verdict, the twelve checks with status and reason, the pending conflict check, and the reasons. PASS is candidate-level only.
  - P7 runs conflict screening, applies the acceptance policy and gives the SPEC §9 outcome for each component. A component with no PASS candidate is an abstention, with the reasons from its reports (for example `source_quality` on a flagged page).
  - A passage-only result is shown as a passage without a verified answer (SPEC §6). It is never ANSWERED.
  - Q11 and Q12 are still open (see the open questions). Neither blocks P7.

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
| 4 | BM25 and exact phrase retrieval reliable | P3 and P4 done (complete-with-limitations). BM25 runs per document (D39). Recall is measured on the three public documents (179 of 180 within K = 50), not on the owner's document (B1). |
| 5 | Supported answer types use extractive selection | P5 |
| 6 | Exact quotations and page citations verifiable | P6 complete. Quotation, location and answer-span checks hold on the synthetic documents and on the three public documents, which is source integrity and not support (SPEC §7). Support on the owner's document is blocked (B1). |
| 7 | Unsupported questions trigger abstention | P7 |
| 8 | Conflicts exposed, not resolved silently | P7 |
| 9 | Evaluation metrics from manually verified data | blocked (B3); harness P8a |
| 10 | Regression tests for discovered failures | P8a (framework), grows as failures are found |
| 11 | Critical functionality runs without a generative LLM, an embedding model or PyTorch (D17) | Done in P0-CLEAN. `tests/unit/test_p0_dependencies.py` enforces the deny-list in the requirement files and `pyproject.toml`, in the imports under `app/`, and in the modules loaded by importing the package. The project venv holds no PyTorch and no model. |
| 12 | Documentation explains limitations and reproducible setup | P10 (README), ARCHITECTURE §8–9 |
