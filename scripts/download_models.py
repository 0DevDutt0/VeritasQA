"""Download the pinned model artifacts and write their manifests (P0-ENV).

Run from the repository root with the project interpreter:

    VeritasQA\\Scripts\\python.exe scripts\\download_models.py          # both models and manifests
    VeritasQA\\Scripts\\python.exe scripts\\download_models.py --nltk   # NLTK punkt_tab only

Each model is pinned to one Hub commit. Every downloaded file is compared with the digest the Hub
publishes for that commit (SHA-256 for LFS files, git blob ID otherwise) before its manifest is
written. Alternate formats (ONNX, OpenVINO, TensorFlow, Rust, Flax and PyTorch .bin copies) are not
downloaded: each model keeps one safetensors copy. The Hub cache is redirected into
models/.hf-home, so the user's shared Hugging Face cache is not used.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "models"
MANIFEST_DIR = MODELS_DIR / "manifests"
sys.path.insert(0, str(REPO_ROOT))

# Redirect every Hub cache location into the project before huggingface_hub is imported.
_HF_HOME = MODELS_DIR / ".hf-home"
os.environ["HF_HOME"] = str(_HF_HOME)
os.environ["HF_HUB_CACHE"] = str(_HF_HOME / "hub")
os.environ["HF_XET_CACHE"] = str(_HF_HOME / "xet")

from app.common import files  # noqa: E402
from app.common.models import (  # noqa: E402
    git_blob_sha1,
    non_generative_problems,
    sha256_file,
    verify_manifest,
)

MODELS: tuple[dict[str, Any], ...] = (
    {
        "name": "all-MiniLM-L6-v2",
        "role": "embedding",
        "purpose": (
            "Compact sentence-embedding encoder for dense-retrieval experiments. Optional: it enters "
            "the pipeline only if the P9a benchmark shows a gain over the BM25 baseline (SPEC §4)."
        ),
        "repo_id": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        "local_dir": "models/embeddings/all-MiniLM-L6-v2",
        "allow_patterns": (
            "1_Pooling/config.json",
            "README.md",
            "config.json",
            "config_sentence_transformers.json",
            "model.safetensors",
            "modules.json",
            "sentence_bert_config.json",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
        ),
    },
    {
        "name": "ms-marco-MiniLM-L6-v2",
        "role": "reranker",
        "purpose": (
            "Cross-encoder that scores a query and a passage together, for reranking candidates. "
            "Optional: a relevance score never establishes factual support (SPEC §4, §9)."
        ),
        "repo_id": "cross-encoder/ms-marco-MiniLM-L6-v2",
        "revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
        "local_dir": "models/rerankers/ms-marco-MiniLM-L6-v2",
        "allow_patterns": (
            "README.md",
            "config.json",
            "model.safetensors",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
        ),
    },
)

_RECORDED_PACKAGES = ("sentence-transformers", "transformers", "huggingface-hub", "safetensors", "torch")


def _installed_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for dist in _RECORDED_PACKAGES:
        try:
            versions[dist] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            versions[dist] = "not installed"
    return versions


def _hub_digest(sibling: Any) -> tuple[str, str]:
    """Return ("sha256", digest) for LFS files, otherwise ("git_blob_sha1", blob id)."""
    lfs = getattr(sibling, "lfs", None)
    sha256 = getattr(lfs, "sha256", None) if lfs is not None else None
    if sha256:
        return "sha256", str(sha256)
    blob_id = getattr(sibling, "blob_id", None)
    if not blob_id:
        raise RuntimeError(f"the Hub publishes no digest for {sibling.rfilename}")
    return "git_blob_sha1", str(blob_id)


def download_model(spec: dict[str, Any]) -> dict[str, Any]:
    """Download one pinned model, verify every file, and write its manifest."""
    from huggingface_hub import HfApi, snapshot_download

    repo_id, revision = spec["repo_id"], spec["revision"]
    info = HfApi().model_info(repo_id, revision=revision, files_metadata=True)
    if info.sha != revision:
        raise RuntimeError(f"Hub returned commit {info.sha} for {repo_id}, expected {revision}")

    wanted = set(spec["allow_patterns"])
    siblings = {sibling.rfilename: sibling for sibling in info.siblings}
    absent = sorted(wanted - siblings.keys())
    if absent:
        raise RuntimeError(f"{repo_id}@{revision} does not contain {absent}")

    local_dir = REPO_ROOT / spec["local_dir"]
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(local_dir),
        allow_patterns=sorted(wanted),
    )

    entries: list[dict[str, Any]] = []
    for rel in sorted(wanted):
        sibling = siblings[rel]
        local_path = local_dir / rel
        if not local_path.is_file():
            raise RuntimeError(f"download did not produce {rel}")
        size = local_path.stat().st_size
        if sibling.size is not None and sibling.size != size:
            raise RuntimeError(f"{rel}: local size {size} differs from Hub size {sibling.size}")
        kind, digest = _hub_digest(sibling)
        actual = sha256_file(local_path) if kind == "sha256" else git_blob_sha1(local_path)
        if actual != digest:
            raise RuntimeError(f"{rel}: local {kind} {actual} differs from Hub {digest}")
        entries.append({"path": rel, "size": size, kind: digest})

    config = files.read_json(local_dir / "config.json")
    architectures = list(config.get("architectures", []))
    pipeline_tag = info.pipeline_tag
    problems = non_generative_problems(architectures, pipeline_tag)
    if problems:
        raise RuntimeError(f"{repo_id} is not accepted as non-generative: {problems}")

    card = getattr(info, "card_data", None)
    license_name = getattr(card, "license", None) if card is not None else None
    if not license_name:
        tagged = [tag.split(":", 1)[1] for tag in (info.tags or []) if tag.startswith("license:")]
        license_name = tagged[0] if tagged else None
    if not license_name:
        raise RuntimeError(f"{repo_id} publishes no licence; it is not accepted")

    manifest: dict[str, Any] = {
        "schema": 1,
        "name": spec["name"],
        "role": spec["role"],
        "purpose": spec["purpose"],
        "repo_id": repo_id,
        "revision": revision,
        "source_url": f"https://huggingface.co/{repo_id}/tree/{revision}",
        "license": license_name,
        "pipeline_tag": pipeline_tag,
        "architectures": architectures,
        "model_type": config.get("model_type"),
        "generative": False,
        "local_dir": spec["local_dir"],
        "expected_storage_bytes": sum(entry["size"] for entry in entries),
        "required_packages": _installed_versions(),
        "not_downloaded_alternate_formats": sorted(set(siblings) - wanted),
        "files": entries,
        "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    verification = verify_manifest(manifest, REPO_ROOT)
    if verification:
        raise RuntimeError(f"manifest does not match local files: {verification}")
    files.write_json(MANIFEST_DIR / f"{spec['name']}.json", manifest)
    return manifest


def download_nltk_punkt_tab() -> None:
    """Fetch only the NLTK sentence-tokenizer resource, into models/nltk_data."""
    import nltk

    target = MODELS_DIR / "nltk_data"
    target.mkdir(parents=True, exist_ok=True)
    nltk.download("punkt_tab", download_dir=str(target), quiet=True, raise_on_error=True)
    resource = target / "tokenizers" / "punkt_tab"
    if not resource.is_dir():
        raise RuntimeError(f"punkt_tab was not installed under {resource}")
    members = [path for path in resource.rglob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in members)
    print(f"OK punkt_tab: {len(members)} files, {total} bytes, at {resource}")


def main(argv: list[str]) -> int:
    print("VeritasQA model download (P0-ENV)")
    if sys.prefix == sys.base_prefix:
        print("RESULT: not a virtual environment. Use the project venv (VeritasQA\\Scripts\\python.exe).")
        return 2
    if "--nltk" in argv:
        download_nltk_punkt_tab()
        return 0
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for spec in MODELS:
        try:
            manifest = download_model(spec)
        except Exception as exc:  # report this model and continue with the next one
            failures += 1
            print(f"FAILED {spec['name']}: {exc}")
            continue
        print(
            f"OK {spec['name']}: {len(manifest['files'])} files, "
            f"{manifest['expected_storage_bytes']} bytes, revision {manifest['revision']}, "
            f"licence {manifest['license']}, architectures {manifest['architectures']}"
        )
    print("RESULT:", "all models downloaded and verified" if not failures else f"{failures} model(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
