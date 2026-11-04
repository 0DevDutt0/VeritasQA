# VeritasQA environment setup

**V1 (D17, 2026-11-04).** VeritasQA V1 is deterministic, LLM-free and embedding-free. It needs only the baseline layer, `requirements.txt`: no GPU, no PyTorch and no model. Sections 1 to 8 record the P0-ENV environment that was built and validated before D17. They are kept as history, and each one is marked where it is historical. Section 9 records the V1 re-verification.

This document explains how to recreate the environment and records what was validated on the development machine. It covers:

1. **Baseline** (`requirements.txt`): the V1 pipeline and the test suite. Required.
2. **Optional TF-IDF and NLP group** (`requirements-experimental.txt`): scikit-learn for the TF-IDF baseline (benchmark-only); spaCy and NLTK, pending the owner's decision (Q6); rapidfuzz, recommended for removal (Q6).
3. **Historical P0-ENV layers** (`requirements-gpu.txt`, `constraints-gpu.txt`, and the two model downloads): removed from the V1 plan (D17). They remain installed in the project venv until P0-CLEAN is approved (Q7).

Nothing in the V1 pipeline imports an optional or historical layer. OCR is out of scope here: Tesseract is not installed (blocker B2 in `PROGRESS.md`).

## 1. Tested environment (development machine; GPU rows are historical, D17)

| Item | Value on the development machine |
| --- | --- |
| OS | Windows 11 Home 10.0.26200 |
| Python | CPython 3.12.10 (python.org Windows installer), SQLite 3.49.1 with FTS5. The lock files were built with 3.12.10. |
| Project venv | `E:\Personal\VeritasQA\VeritasQA` (git-ignored) |
| GPU | NVIDIA GeForce RTX 5090 Laptop GPU, compute capability 12.0 (sm_120), 24,463 MiB |
| NVIDIA driver | 592.01 (`nvidia-smi` reports CUDA 13.1 driver capability) |
| PyTorch | 2.14.1+cu130 (CUDA runtime 13.0) from the PyTorch index |
| RAM | 31.4 GiB installed; about 4.3 GiB free when checked during setup |
| Disk (E:) | 932 GB total; about 550 GB free after the downloads |

**GPU memory is shared.** An Ollama `llama-server` process (PID 31904) was present on the GPU. `nvidia-smi` showed 18,370 MiB in use and 5,768 MiB free when read at the end of setup. In the same second, `torch.cuda.mem_get_info()` reported 23,119 MiB free. The two readings disagree on this Windows (WDDM) machine, and the cause was not established. All validation allocations are under 0.5 GB, so the results do not depend on which figure is right. The GPU validation and model validation both passed under the 5.8 GB reading.

## 2. Layers and what each one provides

| Layer | File | Status under D17 | Imported by the V1 pipeline |
| --- | --- | --- | --- |
| Baseline | `requirements.txt` | V1, necessary: PyMuPDF 1.26.6, pdfplumber 0.11.10, pydantic 2.14.2, pytest 9.2.0 (20 distributions in total, with their dependencies) | Yes |
| TF-IDF (experimental) | `requirements-experimental.txt`: numpy 2.5.4, scikit-learn 1.9.1 | Optional. Benchmark-only (P9a), outside the acceptance path | No |
| NLP (experimental) | `requirements-experimental.txt`: spacy 3.8.18, nltk 3.10.4 | Optional, pending Q6 | No |
| rapidfuzz (experimental) | `requirements-experimental.txt`: rapidfuzz 3.14.6 | Recommended for removal, pending Q6 | No |
| GPU (historical) | `requirements-gpu.txt`, `constraints-gpu.txt`: torch 2.14.1+cu130 | Removed from the V1 plan (D17). Removal pending P0-CLEAN | No |
| Embedding and reranking models (historical) | `scripts/download_models.py`, `models/`: sentence-transformers 6.2.0, transformers 5.22.1, huggingface-hub 2.4.0; all-MiniLM-L6-v2 and ms-marco-MiniLM-L6-v2 | Removed from the V1 plan (D17). Removal pending P0-CLEAN | No |
| Full lock (superseded) | `requirements-validated.txt` | Superseded (D17). Regenerated in P0-CLEAN, not edited | No |

## 3. Reproduce the V1 environment

V1 needs steps 1 and 2 only. Steps 3 to 6 are the historical P0-ENV procedure (D17) and must not be run for V1.

Run these commands from the repository root in PowerShell. In Git Bash, use `VeritasQA/Scripts/python.exe` with forward slashes.

```powershell
# 1. Create the project venv (git-ignored).
py -3.12 -m venv VeritasQA

# 2. Baseline: must install and pass without torch.
VeritasQA\Scripts\python.exe -m pip install -r requirements.txt
VeritasQA\Scripts\python.exe -m pytest -q

# --- Historical (P0-ENV, D17): not part of V1. Do not run the lines below for V1. ---
# 3. GPU group (PyTorch index; pinned).
VeritasQA\Scripts\python.exe -m pip install -r requirements-gpu.txt

# 4. Experimental group, keeping the baseline and torch pins.
VeritasQA\Scripts\python.exe -m pip install -c requirements.txt -c constraints-gpu.txt -r requirements-experimental.txt

# 5. Model artifacts (pinned Hub commits, verified against Hub digests) and the NLTK resource.
VeritasQA\Scripts\python.exe scripts\download_models.py
VeritasQA\Scripts\python.exe scripts\download_models.py --nltk

# 6. Validation.
VeritasQA\Scripts\python.exe scripts\validate_environment.py
VeritasQA\Scripts\python.exe scripts\validate_gpu.py
VeritasQA\Scripts\python.exe scripts\validate_models.py
VeritasQA\Scripts\python.exe -m pytest -q
```

Historical (P0-ENV, D17). To rebuild the whole validated environment in one step from the lock file, use a fresh venv. The lock is superseded and is regenerated in P0-CLEAN:

```powershell
VeritasQA\Scripts\python.exe -m pip install --extra-index-url https://download.pytorch.org/whl/cu130 -r requirements-validated.txt
```

`--extra-index-url` is needed because the torch line is served by the PyTorch index. Every other package comes from PyPI.

## 4. Device selection (`VERITASQA_DEVICE`): historical (D17)

V1 does not read this variable. `app/common/device.py` is removed in P0-CLEAN.

The variable is read from the process environment only. No `.env` file is loaded (`app/common/device.py`, `.env.example`).

| Value | Behaviour |
| --- | --- |
| `auto` (default; also when unset or empty) | `cuda` when a CUDA device is usable, otherwise `cpu` |
| `cuda` | Uses CUDA, or raises `DeviceUnavailableError` with the reason and the next step. It never falls back silently |
| `cpu` | Always the CPU; the GPU is not probed |
| anything else | Raises `DeviceConfigError`. It is not treated as `auto` |

Example: `$env:VERITASQA_DEVICE = "cpu"` in PowerShell.

## 5. Validation results (development machine): historical P0-ENV record

All results below come from commands that were run. Each row names the command.

| Check | Command | Result |
| --- | --- | --- |
| Baseline pins and imports, FTS5, synthetic PDF round trip (PyMuPDF and pdfplumber) | `scripts\validate_environment.py` | `RESULT: baseline valid`. Every baseline pin matches. FTS5 probe passes on SQLite 3.49.1. |
| CUDA kernels for this GPU | `scripts\validate_gpu.py` | `sm_120` is in the wheel's arch list. A 2048×2048 float32 matmul on the GPU, compared with the CPU, has relative error 9.64e-07 (tolerance 1e-4). |
| Model files against manifests | `scripts\validate_models.py`, step 1 | Both models: every file matches its recorded digest. Both are non-generative. |
| Embedder on CUDA | `scripts\validate_models.py`, step 2 | `cuda:0`, output shape (3, 384), all values finite, minimum cosine against CPU 1.000000. |
| Reranker on CUDA | `scripts\validate_models.py`, step 2 | `cuda:0`, output shape (2,), all values finite, max score difference against CPU 2.86e-06. |
| Full test suite, project venv | `pytest -q` | **44 passed**, 0 skipped, in 9.42 s |
| Clean baseline venv (`requirements.txt` only, no torch) | `pytest -q -rs` | **34 passed, 10 skipped** in 0.38 s. Skips: 3 GPU tests, 3 negative-path CUDA tests and 2 model CUDA tests (no PyTorch), and 2 NLP tests (no spaCy or NLTK). `pip check` clean. |
| Fresh clone of `origin/main` (commit `c5d3f61`), section 3 run as written | `pytest -q -rs` at each step | Baseline step: **33 passed, 11 skipped**. The git-ignore test runs and passes in the clone. Skips name the missing torch and model files. After all steps: **44 passed** in 11.10 s. See section 6. |
| Fresh venv rebuilt from `requirements-validated.txt` (commit `f901558`, before the negative-path tests were added) | see section 6 | 41 passed in 13.89 s. Freeze identical to the lock. |

## 6. Full-lock rebuild: historical (the lock is superseded by D17)

A new venv was created from the base Python 3.12.10 install and filled with the lock only:

```powershell
VeritasQA-fresh\Scripts\python.exe -m pip install --extra-index-url https://download.pytorch.org/whl/cu130 -r requirements-validated.txt
```

| Check | Result |
| --- | --- |
| Install | Exit code 0 |
| `pip check` | No broken requirements |
| `pip freeze` against the lock | Identical: 82 packages, same versions |
| torch | 2.14.1+cu130, CUDA 13.0, `torch.cuda.is_available()` True, NVIDIA GeForce RTX 5090 Laptop GPU |
| `pytest -q` (full suite, at commit `f901558`, before the negative-path tests were added) | **41 passed** in 13.89 s, 0 skipped |
| `scripts\validate_environment.py` | `RESULT: baseline valid` |
| `scripts\validate_gpu.py` | `RESULT: GPU validated` (relative error 9.640e-07) |
| `scripts\validate_models.py` | `RESULT: all model checks passed` (cosine vs CPU 1.000000; max score difference 2.86e-06) |

Which groups were rebuilt from scratch: the baseline (section 5, clean venv with `requirements.txt` only) and the whole validated environment, including the GPU and experimental groups (this section). During setup the GPU group was dry-run and then installed into the project venv, and the experimental group was installed into the project venv directly. The fresh rebuild reproduces that state exactly. The scratch venvs are in the session scratchpad, outside the repository.

**Section 3 run as written, in a fresh clone of `origin/main`** (commit `c5d3f61`, PowerShell, `py -3.12` resolves to Python 3.12.10 on this machine). Every command in section 3 was executed, and every step exited 0:

- Steps 1 and 2: `py -3.12 -m venv VeritasQA`, then the baseline install and `pytest -q`. Result: 33 passed, 11 skipped. The skips are the torch-dependent and model-file-dependent tests, which is correct before step 3. The git-ignore test runs and passes.
- Steps 3 and 4: `requirements-gpu.txt`, then the experimental group under the constraints. `pip check` is clean, and torch reports 2.14.1+cu130 with CUDA 13.0 available.
- Step 5: `download_models.py` and `download_models.py --nltk`. Both models verify with the same byte counts as above, and `punkt_tab` has 77 files.
- Step 6: `validate_environment.py` reports `baseline valid`, `validate_gpu.py` reports `GPU validated`, and `validate_models.py` reports `all model checks passed`. `pytest -q` then gives 44 passed in 11.10 s.

That run was made before D17, against the P0-ENV procedure. Section 3 is now the V1 procedure, so that run no longer describes it. The V1 steps were re-verified on 2026-11-04 (section 9).

## 7. Model artifacts: historical (removed from the V1 plan by D17)

Each model is pinned to one Hub commit. `scripts/download_models.py` fetches only the files listed below. It checks each file against the digest the Hub publishes for that commit (SHA-256 for LFS files, git blob ID otherwise). It then writes a manifest under `models/manifests/`. Alternate formats (ONNX, OpenVINO, TensorFlow, Rust, Flax and PyTorch `.bin` copies) are not downloaded.

| Model | Role | Repository and commit | Licence | Architecture (`config.json`) | Pipeline tag | Files | Bytes | `model.safetensors` SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all-MiniLM-L6-v2 | Embedding encoder (optional, benchmark-gated) | `sentence-transformers/all-MiniLM-L6-v2` at `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | Apache-2.0 | `BertModel` | `sentence-similarity` | 11 | 91,578,415 | `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` |
| ms-marco-MiniLM-L6-v2 | Cross-encoder reranker (optional, benchmark-gated) | `cross-encoder/ms-marco-MiniLM-L6-v2` at `233902d25c440f23af6f7d6e94d2946bac0bee0a` | Apache-2.0 | `BertForSequenceClassification` | `text-ranking` | 7 | 91,819,431 | `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae` |

Both models are encoder or classifier architectures. Neither has a language-model generation head. Their manifests record this, and the tests reject any architecture or pipeline tag that implies generation (`app/common/models.py`).

The NLTK resource `punkt_tab` (sentence tokenizer, 77 extracted files, 10,885,330 bytes, plus the 4,319,076-byte archive) is stored under `models/nltk_data/`. It was fetched with `scripts\download_models.py --nltk`. This project does not verify its digests, because NLTK does not publish manifests in the same form.

**Downloaded is not validated for use.** Both models were downloaded, loaded from their local directories with the Hub offline, and run on the GPU and the CPU. Neither has been benchmarked. Neither enters the V1 pipeline: D17 removes both from the V1 plan, so the benchmark gate no longer applies to them.

## 8. Known limitations

- The GPU is a laptop variant of the RTX 5090. Results were measured on this device only.
- GPU memory is shared with other processes on this machine (section 1). Free-memory figures from the two tools disagree, and the cause was not established.
- Only the matmul kernel and the two models were run on the GPU. No training, no mixed precision and no multi-GPU run was tested.
- The NLTK resource is not checksum-verified by this project (section 7).
- Tesseract OCR is not installed (blocker B2). No GPU OCR library or model was installed.
- PyMuPDF is AGPL-3.0 or commercially licensed (question Q4 in `PROGRESS.md`).
- The optional packages are validated for installation, import and the smoke tests above. Their use in the pipeline is not validated yet.

## 9. V1 re-verification (2026-11-04, after D17)

Section 3, steps 1 and 2, were run as written. The baseline ran in a scratch venv under the session scratchpad, outside the repository, built with the base Python 3.12.10 interpreter. No GPU and no model were installed in it.

| Check | Command | Result |
| --- | --- | --- |
| Baseline install | `python -m pip install -r requirements.txt` | Exit code 0 |
| Dependency check | `python -m pip check` | No broken requirements found |
| Test suite | `python -m pytest -q` | 34 passed, 10 skipped in 0.31 s |
| torch present | `importlib.util.find_spec("torch")` | False |
| Freeze | `python -m pip freeze --exclude pip` | 20 packages, the baseline closure |
| Venv size | `du -sh` | 137 MB on disk |

The project venv, which still holds the P0-ENV packages, was also checked the same day, after the documentation change:

| Check | Command | Result |
| --- | --- | --- |
| Full suite | `python -m pytest -q` | 44 passed in 10.19 s |
| Baseline validator | `scripts\validate_environment.py` | `RESULT: baseline valid`, exit 0 |
