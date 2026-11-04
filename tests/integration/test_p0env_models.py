"""P0-ENV: downloaded model artifacts match their manifests and run on CUDA and CPU.

Each model is loaded from its local directory with the Hub offline. Nothing is fetched by repo ID.
The GPU tests are skipped when CUDA is absent, and all tests are skipped when no manifest exists.

Run:  pytest tests/integration/test_p0env_models.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.common.models import (
    load_manifest,
    non_generative_problems,
    smoke_test_embedder,
    smoke_test_reranker,
    verify_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO_ROOT / "models" / "manifests"

pytestmark = pytest.mark.integration


def _manifest(name: str) -> dict:
    return load_manifest(MANIFEST_DIR / f"{name}.json")


@pytest.mark.requires_models
def test_every_local_file_matches_its_manifest():
    problems: list[str] = []
    for path in sorted(MANIFEST_DIR.glob("*.json")):
        problems += verify_manifest(load_manifest(path), REPO_ROOT)
    assert problems == []


def test_every_manifested_model_is_non_generative():
    # Reads only the tracked manifests, so it runs on a fresh clone without weights.
    for path in sorted(MANIFEST_DIR.glob("*.json")):
        manifest = load_manifest(path)
        assert manifest["generative"] is False
        assert non_generative_problems(manifest["architectures"], manifest["pipeline_tag"]) == []


@pytest.mark.requires_models
@pytest.mark.requires_cuda
def test_embedder_runs_on_cuda_and_matches_cpu():
    manifest = _manifest("all-MiniLM-L6-v2")
    result = smoke_test_embedder(REPO_ROOT / manifest["local_dir"], "cuda", name=manifest["name"])
    assert result.device_used.startswith("cuda"), result
    assert result.passed, result


@pytest.mark.requires_models
@pytest.mark.requires_cuda
def test_reranker_runs_on_cuda_and_matches_cpu():
    manifest = _manifest("ms-marco-MiniLM-L6-v2")
    result = smoke_test_reranker(REPO_ROOT / manifest["local_dir"], "cuda", name=manifest["name"])
    assert result.device_used.startswith("cuda"), result
    assert result.passed, result
