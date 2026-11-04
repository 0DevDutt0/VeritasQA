# models/

Local model artifacts for the optional neural components (SPEC §4). Weights are never committed.
Only this README and the JSON manifests under `manifests/` are tracked.

| Path | Contents | In git |
| --- | --- | --- |
| `embeddings/` | Sentence-embedding encoder (optional, benchmark-gated) | No (weights) |
| `rerankers/` | Cross-encoder reranker (optional, benchmark-gated) | No (weights) |
| `manifests/` | One JSON record per model: repository, pinned commit, licence, architectures, file digests | Yes |
| `nltk_data/` | NLTK tokenizer resource (`punkt_tab`) | No |
| `.hf-home/` | Hugging Face cache used by `scripts/download_models.py` | No |

No GPU OCR model is installed. Tesseract is the OCR fallback (SPEC §3A) and is not installed on the
development machine (blocker B2 in `PROGRESS.md`).

## Rules

1. Pin every model to a Hub commit. Record its licence and the evidence that it is non-generative
   (`architectures` from `config.json` and an accepted `pipeline_tag`).
2. Download only with `scripts/download_models.py`. Verify with `scripts/validate_models.py`.
3. Load models only from their local directories, with `HF_HUB_OFFLINE=1`. Never load by repo ID.
4. Keep weights out of `.venv` and out of git. The `.gitignore` rules cover `models/**` and the
   weight formats, and keep the manifests tracked.
5. A downloaded model is not a validated component. A model enters the pipeline only after a
   benchmark on the development split shows a gain over the BM25 baseline (SPEC §4, §9, P9a).
