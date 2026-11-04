# models/

V1 loads no model (D17). This folder holds no model artifact. The P0-ENV artifacts (the two embedding and reranking models, the NLTK `punkt_tab` resource, the Hugging Face download cache and the manifests) were removed in P0-CLEAN, after the owner approved the cleanup (Q7, 2026-11-04). The last commit that holds them is `e57c443`. `git show e57c443:models/manifests/all-MiniLM-L6-v2.json` restores a record.

Only this README is tracked. Weights, caches and downloaded resources are never committed. `.gitignore` covers `models/**`, the weight formats and `nltk_data/` as a guard.

No GPU OCR model is installed. Tesseract is the OCR fallback (SPEC §3A) and is not installed on the development machine (blocker B2 in `PROGRESS.md`).

## Rules

1. A V1 pipeline loads no model (D17). A future model needs an owner decision, a SPEC revision and a benchmark on the development split that shows a gain over the BM25 baseline (SPEC §4, §9).
2. If a model is ever admitted, pin it to a Hub commit, and record its licence, its digests and the evidence that it is non-generative in a tracked manifest. The `.gitignore` rules need a re-include for that manifest.
3. Keep weights out of `.venv` and out of git. The `.gitignore` rules stay as a guard.
