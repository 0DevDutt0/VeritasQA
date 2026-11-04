# VeritasQA environment setup

**Scope (V1, D17).** VeritasQA V1 is deterministic, LLM-free and embedding-free. It needs only the baseline, `requirements.txt`: no GPU, no PyTorch, no spaCy or NLTK, and no model. The optional TF-IDF group (`requirements-experimental.txt`) is installed in the project venv so that the benchmark-only P9a baseline can run. No pipeline module imports it.

The P0-ENV GPU and model layers were removed in P0-CLEAN (2026-11-04). Their validation record is in `PROGRESS.md`, and their files are in git history up to commit `e57c443`.

OCR is out of scope here: Tesseract is not installed (blocker B2 in `PROGRESS.md`).

## 1. Requirements

| Item | Value |
| --- | --- |
| OS | Windows 11 (the development machine). The commands below are PowerShell. In Git Bash, use `VeritasQA/Scripts/python.exe` with forward slashes. |
| Python | CPython 3.11 or later. The lock was produced with CPython 3.12.10 (python.org Windows installer). |
| SQLite | Built with FTS5. The startup check in `app/storage/fts5.py` reports a build without it. The development build is SQLite 3.49.1. |
| Project venv | `VeritasQA\` in the repository root. It is git-ignored and is not part of the project. |

## 2. Layers

| Layer | File | Status | Imported by the V1 pipeline |
| --- | --- | --- | --- |
| Baseline | `requirements.txt`: PyMuPDF 1.26.6, pdfplumber 0.11.10, pydantic 2.14.2, pytest 9.2.0 | V1, necessary. 20 distributions with their dependencies. No NumPy. | Yes |
| TF-IDF (optional) | `requirements-experimental.txt`: numpy 2.5.4, scikit-learn 1.9.1 | Benchmark-only (P9a), outside the acceptance path | No |
| Lock | `requirements-validated.txt`: 27 pins, the baseline and the optional group | The full project venv at exact versions. Regenerated from a fresh venv (section 4). Never edited by hand | No |

Removed by P0-CLEAN (D17 and the owner's decision Q6): PyTorch and CUDA, sentence-transformers and the two embedding and reranking models, spaCy, NLTK with `punkt_tab`, and rapidfuzz.

## 3. Create the V1 environment

Run these commands from the repository root in PowerShell.

```powershell
# 1. Create the project venv (git-ignored).
py -3.12 -m venv VeritasQA

# 2. Install the exact validated environment (the baseline plus the optional TF-IDF group).
VeritasQA\Scripts\python.exe -m pip install -r requirements-validated.txt

# 3. Check the dependencies, run the tests and run the baseline validator.
VeritasQA\Scripts\python.exe -m pip check
VeritasQA\Scripts\python.exe -m pytest -q
VeritasQA\Scripts\python.exe scripts\validate_environment.py
```

For the baseline alone, install `requirements.txt` in step 2 instead. The baseline suite passes without the optional group, and `pip check` is clean in both cases.

## 4. Regenerate the lock

Use this procedure after any pin change in `requirements.txt` or `requirements-experimental.txt`. Never edit `requirements-validated.txt` by hand.

1. Build a fresh venv outside the repository, from the two requirement files, then check it:

   ```powershell
   py -3.12 -m venv <scratch-venv>
   <scratch-venv>\Scripts\python.exe -m pip install -r requirements.txt -r requirements-experimental.txt
   <scratch-venv>\Scripts\python.exe -m pip check
   <scratch-venv>\Scripts\python.exe -m pytest -q
   ```

2. Write the freeze to the lock. On Windows, `pip freeze` writes CRLF line endings when its output is redirected, so strip the carriage returns. The lock is UTF-8 with LF line endings and no BOM (D8). Keep its comment header:

   ```bash
   grep '^#' requirements-validated.txt > header.txt
   <scratch-venv>/Scripts/python.exe -m pip freeze --exclude pip | tr -d '\r' > body.txt
   cat header.txt body.txt > requirements-validated.txt
   ```

3. Rebuild the project venv from the lock, and check that its freeze equals the lock, ignoring comments:

   ```bash
   VeritasQA/Scripts/python.exe -m pip install -r requirements-validated.txt
   diff <(grep -v '^#' requirements-validated.txt | sort) <(VeritasQA/Scripts/python.exe -m pip freeze --exclude pip | tr -d '\r' | sort)
   ```

## 5. The V1 rule (deny-list)

`tests/unit/test_p0_dependencies.py` enforces D17 and Q6:

- No requirement file and no `pyproject.toml` dependency may name torch, torchvision, torchaudio, sentence-transformers, transformers, huggingface-hub, tokenizers, safetensors, faiss, chromadb, openai, anthropic, spacy, nltk or rapidfuzz.
- No module under `app/` may import them, and importing the package may not load them.
- The lock must carry every declared pin at the same version.

Run only this check with `VeritasQA\Scripts\python.exe -m pytest -q tests\unit\test_p0_dependencies.py`.

## 6. Validation record (P0-CLEAN, 2026-11-04)

| Check | Command | Result |
| --- | --- | --- |
| Baseline only, scratch venv (20 packages) | `pip install -r requirements.txt`; `pip check`; `pytest -q -rs --ignore=tests/unit/test_p0_dependencies.py` | No broken requirements. `7 passed`, 0 skipped. The deny-list file was excluded, because the old lock still existed at that stage. |
| Baseline and optional group, scratch venv | `pip install -r requirements-experimental.txt`; `pip check`; `pytest -q` | No broken requirements. `16 passed`. |
| Project venv rebuilt from the lock | `pip install -r requirements-validated.txt`; `pip check`; `pytest -q -rs`; freeze compared with the lock | No broken requirements. `16 passed`, 0 skipped. Freeze identical to the lock. |
| Baseline validator | `scripts\validate_environment.py` | `RESULT: baseline valid`, exit 0 |
| Fresh clone of `origin/main` (commit `6fa490a`), section 3 run as written, with the base Python 3.12.10 interpreter in place of `py -3.12` | Baseline only: `pip install -r requirements.txt`, `pip check`, `pytest -q -rs`, `scripts\validate_environment.py`. Then `pip install -r requirements-validated.txt` in the same venv, `pip check`, freeze compared with the lock, `pytest -q -rs`, `scripts\validate_environment.py` | Baseline only: no broken requirements; `16 passed`, 0 skipped; `RESULT: baseline valid`. Lock: no broken requirements; freeze identical to the lock; `16 passed`, 0 skipped; `RESULT: baseline valid`. The clone stayed clean. |

The project venv measures 377 MB on disk, against 3.7 GB before the cleanup.

## 7. Known limitations

- The lock is the freeze of one machine (Windows 11, CPython 3.12.10). Another platform needs its own lock.
- The optional group is installed, but no pipeline module uses it. Its use in the pipeline is validated only in P9a.
- Tesseract OCR is not installed (blocker B2).
- PyMuPDF is AGPL-3.0 or commercially licensed (question Q4 in `PROGRESS.md`).
- The deny-list test cannot see imports built at run time, such as `importlib.import_module` with a computed name.
