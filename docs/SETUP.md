# VeritasQA environment setup (P0-ENV)

This document explains how to recreate the development environment and records what was validated on the development machine. It covers three layers:

1. **Baseline** (`requirements.txt`): the CPU pipeline and the test suite. No GPU, PyTorch or model is needed.
2. **GPU group** (`requirements-gpu.txt`, `constraints-gpu.txt`): PyTorch with CUDA, for the optional neural components.
3. **Experimental group** (`requirements-experimental.txt`): NumPy, scikit-learn, spaCy, NLTK, rapidfuzz and sentence-transformers, for the benchmark phase (SPEC §4, §9, P9a).

Nothing in the baseline pipeline imports the GPU or experimental groups. Model weights are stored under `models/` and are never committed. OCR is out of scope here: Tesseract is not installed (blocker B2 in `PROGRESS.md`).

## 1. Tested environment

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

| Layer | File | Installed into the project venv | Imported by the baseline pipeline |
| --- | --- | --- | --- |
| Baseline | `requirements.txt` | PyMuPDF 1.26.6, pdfplumber 0.11.10, pydantic 2.14.2, pytest 9.2.0 | Yes |
| GPU | `requirements-gpu.txt`, `constraints-gpu.txt` | torch 2.14.1+cu130 (no torchvision, no torchaudio) | No |
| Experimental | `requirements-experimental.txt` | numpy 2.5.4, scikit-learn 1.9.1, spacy 3.8.18, nltk 3.10.4, rapidfuzz 3.14.6, sentence-transformers 6.2.0, huggingface-hub 2.4.0 | No |
| Full lock | `requirements-validated.txt` | Every package above and its transitive dependencies, at exact versions (82 entries) | No |

## 3. Reproduce the environment

Run these commands from the repository root in PowerShell. In Git Bash, use `VeritasQA/Scripts/python.exe` with forward slashes.

```powershell
# 1. Create the project venv (git-ignored).
py -3.12 -m venv VeritasQA

# 2. Baseline: must install and pass without torch.
VeritasQA\Scripts\python.exe -m pip install -r requirements.txt
VeritasQA\Scripts\python.exe -m pytest -q

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

To rebuild the whole validated environment in one step from the lock file, use a fresh venv:

```powershell
VeritasQA\Scripts\python.exe -m pip install --extra-index-url https://download.pytorch.org/whl/cu130 -r requirements-validated.txt
```

`--extra-index-url` is needed because the torch line is served by the PyTorch index. Every other package comes from PyPI.

## 4. Device selection (`VERITASQA_DEVICE`)

The variable is read from the process environment only. No `.env` file is loaded (`app/common/device.py`, `.env.example`).

| Value | Behaviour |
| --- | --- |
| `auto` (default; also when unset or empty) | `cuda` when a CUDA device is usable, otherwise `cpu` |
| `cuda` | Uses CUDA, or raises `DeviceUnavailableError` with the reason and the next step. It never falls back silently |
| `cpu` | Always the CPU; the GPU is not probed |
| anything else | Raises `DeviceConfigError`. It is not treated as `auto` |

Example: `$env:VERITASQA_DEVICE = "cpu"` in PowerShell.

## 5. Validation results (development machine)

All results below come from commands that were run. Each row names the command.

| Check | Command | Result |
| --- | --- | --- |
| Baseline pins and imports, FTS5, synthetic PDF round trip (PyMuPDF and pdfplumber) | `scripts\validate_environment.py` | `RESULT: baseline valid`. Every baseline pin matches. FTS5 probe passes on SQLite 3.49.1. |
| CUDA kernels for this GPU | `scripts\validate_gpu.py` | `sm_120` is in the wheel's arch list. A 2048×2048 float32 matmul on the GPU, compared with the CPU, has relative error 9.64e-07 (tolerance 1e-4). |
| Model files against manifests | `scripts\validate_models.py`, step 1 | Both models: every file matches its recorded digest. Both are non-generative. |
| Embedder on CUDA | `scripts\validate_models.py`, step 2 | `cuda:0`, output shape (3, 384), all values finite, minimum cosine against CPU 1.000000. |
| Reranker on CUDA | `scripts\validate_models.py`, step 2 | `cuda:0`, output shape (2,), all values finite, max score difference against CPU 2.86e-06. |
| Full test suite, project venv | `pytest -q` | **41 passed**, 0 skipped, in 7.08 s |
| Clean baseline venv (`requirements.txt` only, no torch) | `pytest -q -rs` | **34 passed, 7 skipped** in 0.31 s. Skips: 3 GPU tests and 2 model CUDA tests (no PyTorch), 2 NLP tests (no spaCy or NLTK). `pip check` clean. |
| Fresh-clone simulation (tracked files only, no weights, not a git repo) | `pytest -q -rs` in a copy | 32 passed, 9 skipped. Skip reasons name the missing model files and the missing CUDA device. |
| Fresh venv rebuilt from `requirements-validated.txt` | see section 6 | See section 6. |

## 6. Full-lock rebuild

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
| `pytest -q` (full suite) | **41 passed** in 13.89 s, 0 skipped |
| `scripts\validate_environment.py` | `RESULT: baseline valid` |
| `scripts\validate_gpu.py` | `RESULT: GPU validated` (relative error 9.640e-07) |
| `scripts\validate_models.py` | `RESULT: all model checks passed` (cosine vs CPU 1.000000; max score difference 2.86e-06) |

Which groups were rebuilt from scratch: the baseline (section 5, clean venv with `requirements.txt` only) and the whole validated environment, including the GPU and experimental groups (this section). During setup the GPU group was dry-run and then installed into the project venv, and the experimental group was installed into the project venv directly. The fresh rebuild reproduces that state exactly. The scratch venvs are in the session scratchpad, outside the repository.

## 7. Model artifacts

Each model is pinned to one Hub commit. `scripts/download_models.py` fetches only the files listed below. It checks each file against the digest the Hub publishes for that commit (SHA-256 for LFS files, git blob ID otherwise). It then writes a manifest under `models/manifests/`. Alternate formats (ONNX, OpenVINO, TensorFlow, Rust, Flax and PyTorch `.bin` copies) are not downloaded.

| Model | Role | Repository and commit | Licence | Architecture (`config.json`) | Pipeline tag | Files | Bytes | `model.safetensors` SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all-MiniLM-L6-v2 | Embedding encoder (optional, benchmark-gated) | `sentence-transformers/all-MiniLM-L6-v2` at `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | Apache-2.0 | `BertModel` | `sentence-similarity` | 11 | 91,578,415 | `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` |
| ms-marco-MiniLM-L6-v2 | Cross-encoder reranker (optional, benchmark-gated) | `cross-encoder/ms-marco-MiniLM-L6-v2` at `233902d25c440f23af6f7d6e94d2946bac0bee0a` | Apache-2.0 | `BertForSequenceClassification` | `text-ranking` | 7 | 91,819,431 | `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae` |

Both models are encoder or classifier architectures. Neither has a language-model generation head. Their manifests record this, and the tests reject any architecture or pipeline tag that implies generation (`app/common/models.py`).

The NLTK resource `punkt_tab` (sentence tokenizer, 77 extracted files, 10,885,330 bytes, plus the 4,319,076-byte archive) is stored under `models/nltk_data/`. It was fetched with `scripts\download_models.py --nltk`. This project does not verify its digests, because NLTK does not publish manifests in the same form.

**Downloaded is not validated for use.** Both models were downloaded, loaded from their local directories with the Hub offline, and run on the GPU and the CPU. Neither has been benchmarked. Neither enters the pipeline until a benchmark on the development split shows a gain over the BM25 baseline (SPEC §4, §9; P9a).

## 8. Known limitations

- The GPU is a laptop variant of the RTX 5090. Results were measured on this device only.
- GPU memory is shared with other processes on this machine (section 1). Free-memory figures from the two tools disagree, and the cause was not established.
- Only the matmul kernel and the two models were run on the GPU. No training, no mixed precision and no multi-GPU run was tested.
- The NLTK resource is not checksum-verified by this project (section 7).
- Tesseract OCR is not installed (blocker B2). No GPU OCR library or model was installed.
- PyMuPDF is AGPL-3.0 or commercially licensed (question Q4 in `PROGRESS.md`).
- The optional packages are validated for installation, import and the smoke tests above. Their use in the pipeline is not validated yet.
