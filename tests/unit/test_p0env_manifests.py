"""P0-ENV: manifest rules and tamper detection. CPU-only; synthetic files are labelled as such.

Run:  pytest tests/unit/test_p0env_manifests.py -q
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.common.models import (
    git_blob_sha1,
    load_manifest,
    non_generative_problems,
    sha256_file,
    verify_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO_ROOT / "models" / "manifests"
REQUIRED_KEYS = {
    "name",
    "role",
    "purpose",
    "repo_id",
    "revision",
    "source_url",
    "license",
    "pipeline_tag",
    "architectures",
    "generative",
    "local_dir",
    "files",
    "downloaded_utc",
    "required_packages",
}


def test_generation_architectures_and_tasks_are_rejected():
    assert non_generative_problems(["BertModel"], "sentence-similarity") == []
    assert non_generative_problems(["BertForSequenceClassification"], "text-ranking") == []
    assert non_generative_problems(["LlamaForCausalLM"], "text-generation")
    assert non_generative_problems(["T5ForConditionalGeneration"], "text2text-generation")
    assert non_generative_problems(["BertModel"], "text-generation")
    assert non_generative_problems([], "sentence-similarity")


def test_tracked_manifests_have_complete_non_generative_records():
    paths = sorted(MANIFEST_DIR.glob("*.json"))
    assert paths, "expected at least one manifest under models/manifests"
    for path in paths:
        manifest = load_manifest(path)
        missing = REQUIRED_KEYS - manifest.keys()
        assert not missing, f"{path.name} lacks {sorted(missing)}"
        assert manifest["generative"] is False
        assert non_generative_problems(manifest["architectures"], manifest["pipeline_tag"]) == []
        assert len(manifest["revision"]) == 40
        assert manifest["files"], f"{path.name} lists no files"
        for entry in manifest["files"]:
            digest = entry.get("sha256") or entry.get("git_blob_sha1")
            assert digest and len(digest) in (40, 64), f"{path.name}: bad digest for {entry['path']}"


def test_verify_manifest_accepts_matching_files_and_detects_tampering(tmp_path):
    # Synthetic fixture: a small file stands in for a model artifact.
    local = tmp_path / "models" / "synthetic"
    local.mkdir(parents=True)
    payload = local / "weights.safetensors"
    payload.write_bytes(b"synthetic weights v1")
    config = local / "config.json"
    config.write_text(json.dumps({"architectures": ["BertModel"]}), encoding="utf-8")

    manifest = {
        "name": "synthetic",
        "generative": False,
        "architectures": ["BertModel"],
        "pipeline_tag": "sentence-similarity",
        "revision": "0" * 40,
        "local_dir": "models/synthetic",
        "files": [
            {
                "path": "weights.safetensors",
                "size": payload.stat().st_size,
                "sha256": sha256_file(payload),
            },
            {"path": "config.json", "size": config.stat().st_size, "git_blob_sha1": git_blob_sha1(config)},
        ],
    }
    assert verify_manifest(manifest, tmp_path) == []

    payload.write_bytes(b"synthetic weights v2")  # same length, different content
    problems = verify_manifest(manifest, tmp_path)
    assert any("SHA-256" in p and "weights.safetensors" in p for p in problems), problems

    payload.unlink()
    problems = verify_manifest(manifest, tmp_path)
    assert any("missing file weights.safetensors" in p for p in problems), problems


def test_verify_manifest_rejects_a_generative_record(tmp_path):
    manifest = {
        "name": "synthetic-generator",
        "generative": True,
        "architectures": ["LlamaForCausalLM"],
        "pipeline_tag": "text-generation",
        "revision": "0" * 40,
        "local_dir": "models/none",
        "files": [{"path": "x.bin", "size": 1, "sha256": "0" * 64}],
    }
    problems = verify_manifest(manifest, tmp_path)
    assert any("generative: false" in p for p in problems)
    assert any("CausalLM" in p for p in problems)


def _inside_git_worktree() -> bool:
    if shutil.which("git") is None:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


@pytest.mark.skipif(not _inside_git_worktree(), reason="not inside a git work tree")
def test_weights_are_git_ignored_and_manifests_are_tracked():
    def ignored(path: str) -> bool:
        # -q with no -v: exit 0 means ignored, exit 1 means not ignored (negated rules return 1).
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", path],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        return result.returncode == 0

    assert ignored("models/embeddings/all-MiniLM-L6-v2/model.safetensors")
    assert ignored("models/rerankers/ms-marco-MiniLM-L6-v2/pytorch_model.bin")
    assert ignored(".env")
    assert not ignored("models/manifests/all-MiniLM-L6-v2.json")
    assert not ignored(".env.example")
