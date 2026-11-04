# models/

V1 loads no model (D17). This folder holds artifacts from the historical P0-ENV phase. They are outside the V1 plan and are slated for removal in P0-CLEAN, pending the owner's approval (Q7). Weights are never committed.
Only this README and the JSON manifests under `manifests/` are tracked.

| Path | Contents | V1 status | In git |
| --- | --- | --- | --- |
| `embeddings/` | Sentence-embedding encoder from P0-ENV | Removed from the V1 plan (D17); removal pending | No (weights) |
| `rerankers/` | Cross-encoder reranker from P0-ENV | Removed from the V1 plan (D17); removal pending | No (weights) |
| `manifests/` | One JSON record per P0-ENV model | Historical; removal pending, together with its test | Yes |
| `nltk_data/` | NLTK `punkt_tab` sentence resource | Optional; kept or removed with the NLP decision (Q6). This project does not verify its digests | No |
| `.hf-home/` | Hugging Face download cache from `scripts/download_models.py` | Historical; removal pending | No |

No GPU OCR model is installed. Tesseract is the OCR fallback (SPEC §3A) and is not installed on the development machine (blocker B2 in `PROGRESS.md`).

## Rules

1. A V1 pipeline loads no model (D17). A future model needs an owner decision, a SPEC revision and a benchmark on the development split that shows a gain over the BM25 baseline (SPEC §4, §9).
2. If a model is ever admitted, pin it to a Hub commit and record its licence and the evidence that it is non-generative, in a manifest.
3. The historical download and validation scripts (`scripts/download_models.py`, `scripts/validate_models.py`) stay in the repository only until P0-CLEAN.
4. Keep weights out of `.venv` and out of git. The `.gitignore` rules cover `models/**` and the weight formats, and keep the manifests tracked. These rules stay after the cleanup as a guard.
