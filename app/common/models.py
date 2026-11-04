"""Model artifacts: manifests, integrity checks and CUDA smoke tests (P0-ENV).

A manifest (``models/manifests/<name>.json``) is the tracked record of one downloaded model. It
holds the Hub repository, the pinned commit, the licence, the architectures and the digest of
every file kept locally. Weights are never committed. This module checks that a local copy
matches its manifest, and that the model is a non-generative encoder or classifier (SPEC §1).

Smoke tests load a model only from its local directory, with the Hub offline, and run it on the
requested device. They also compare the GPU output with a CPU run of the same model.
"""

from __future__ import annotations

import gc
import hashlib
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.common import files
from app.common.errors import VeritasQAError

# Hub pipeline tags that describe non-generative use: encoders, rankers and classifiers.
ACCEPTED_PIPELINE_TAGS = frozenset(
    {"sentence-similarity", "feature-extraction", "text-ranking", "text-classification"}
)
# Architecture names that imply autoregressive or sequence-to-sequence text generation.
GENERATION_MARKERS = ("CausalLM", "LMHead", "ConditionalGeneration", "Seq2Seq", "Generation")

EMBEDDING_MIN_COSINE = 0.999  # GPU vs CPU embeddings for the same input
RERANKER_MAX_ABS_DIFF = 1e-3  # GPU vs CPU relevance logits for the same pairs

EMBED_PROBE_SENTENCES = (
    "The warranty period is 24 months from delivery.",
    "Invoices are payable within 30 days.",
    "Warranty claims must be filed in writing.",
)
RERANK_PROBE_PAIRS = (
    ("How long is the warranty period?", "The warranty period is 24 months from delivery."),
    ("How long is the warranty period?", "Invoices are payable within 30 days."),
)

_SHA1_HEX = re.compile(r"^[0-9a-f]{40}$")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_CHUNK_BYTES = 1 << 20


class ModelArtifactError(VeritasQAError):
    """A model artifact is missing, altered, or not an accepted non-generative model."""


@dataclass(frozen=True)
class ModelSmokeResult:
    """Outcome of loading one model on a device and running it on fixed probe inputs."""

    model: str
    device_requested: str
    device_used: str
    output_shape: tuple[int, ...]
    finite: bool
    parity_metric: float  # min cosine (embedder) or max absolute score difference (reranker)
    parity_passed: bool
    passed: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    """Git's object ID for a file: SHA-1 of ``blob <size>`` NUL, then the content."""
    digest = hashlib.sha1(f"blob {path.stat().st_size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = files.read_json(path)
    if not isinstance(manifest, dict):
        raise ModelArtifactError(f"{path} does not contain a JSON object")
    return manifest


def non_generative_problems(architectures: Sequence[str], pipeline_tag: str | None) -> list[str]:
    """Reasons a model cannot be used as a non-generative component. An empty list means accepted."""
    problems: list[str] = []
    if not architectures:
        problems.append("no architecture is recorded")
    for name in architectures:
        for marker in GENERATION_MARKERS:
            if marker in name:
                problems.append(f"architecture {name!r} contains the generation marker {marker!r}")
    if pipeline_tag not in ACCEPTED_PIPELINE_TAGS:
        problems.append(f"pipeline tag {pipeline_tag!r} is not an accepted non-generative task")
    return problems


def verify_manifest(manifest: dict[str, Any], repo_root: Path) -> list[str]:
    """Check a manifest and the local files it describes. An empty list means everything matches."""
    name = str(manifest.get("name", "<unnamed>"))
    problems: list[str] = []
    if manifest.get("generative") is not False:
        problems.append(f"{name}: manifest must declare generative: false")
    for reason in non_generative_problems(manifest.get("architectures", []), manifest.get("pipeline_tag")):
        problems.append(f"{name}: {reason}")
    if not _SHA1_HEX.match(str(manifest.get("revision", ""))):
        problems.append(f"{name}: revision is not a 40-character commit SHA")

    entries = manifest.get("files", [])
    if not entries:
        problems.append(f"{name}: no files are listed")
    local_dir = repo_root / str(manifest.get("local_dir", ""))
    for entry in entries:
        rel = entry["path"]
        target = local_dir / rel
        if not target.is_file():
            problems.append(f"{name}: missing file {rel}")
            continue
        if target.stat().st_size != entry["size"]:
            problems.append(f"{name}: size differs from the manifest for {rel}")
        if "sha256" in entry:
            if not _SHA256_HEX.match(entry["sha256"]) or sha256_file(target) != entry["sha256"]:
                problems.append(f"{name}: SHA-256 differs from the manifest for {rel}")
        elif "git_blob_sha1" in entry:
            if not _SHA1_HEX.match(entry["git_blob_sha1"]) or git_blob_sha1(target) != entry["git_blob_sha1"]:
                problems.append(f"{name}: git blob ID differs from the manifest for {rel}")
        else:
            problems.append(f"{name}: no digest is recorded for {rel}")
    return problems


def _load_offline() -> None:
    """Load from local paths only: no network access from huggingface_hub or transformers."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def _release(device: str) -> None:
    """Free the model's VRAM before the next model is loaded."""
    import torch

    gc.collect()
    if device == "cuda":
        torch.cuda.synchronize()
        torch.cuda.empty_cache()


def smoke_test_embedder(model_dir: Path, device: str, *, name: str = "embedder") -> ModelSmokeResult:
    """Encode fixed sentences on ``device`` and compare each vector with the CPU vector."""
    _load_offline()
    import torch
    from sentence_transformers import SentenceTransformer

    sentences = list(EMBED_PROBE_SENTENCES)
    model = SentenceTransformer(str(model_dir), device=device)
    try:
        device_used = str(model.device)
        vectors = model.encode(sentences, convert_to_tensor=True, normalize_embeddings=True)
        output_shape = tuple(vectors.shape)
        gpu_array = vectors.detach().float().cpu()
        del vectors
    finally:
        del model
        _release(device)

    cpu_model = SentenceTransformer(str(model_dir), device="cpu")
    try:
        cpu_array = (
            cpu_model.encode(sentences, convert_to_tensor=True, normalize_embeddings=True)
            .detach()
            .float()
            .cpu()
        )
    finally:
        del cpu_model
        _release("cpu")

    finite = bool(torch.isfinite(gpu_array).all())
    min_cosine = float(torch.nn.functional.cosine_similarity(gpu_array, cpu_array, dim=1).min())
    parity_passed = min_cosine >= EMBEDDING_MIN_COSINE
    shape_ok = output_shape == (len(sentences), output_shape[1]) and output_shape[1] > 0
    device_ok = device_used.startswith(device) if device != "cpu" else True
    return ModelSmokeResult(
        model=name,
        device_requested=device,
        device_used=device_used,
        output_shape=output_shape,
        finite=finite,
        parity_metric=min_cosine,
        parity_passed=parity_passed,
        passed=finite and parity_passed and shape_ok and device_ok,
    )


def smoke_test_reranker(model_dir: Path, device: str, *, name: str = "reranker") -> ModelSmokeResult:
    """Score fixed query-passage pairs on ``device`` and compare the scores with the CPU scores."""
    _load_offline()
    import numpy as np
    from sentence_transformers import CrossEncoder

    pairs = [list(pair) for pair in RERANK_PROBE_PAIRS]
    model = CrossEncoder(str(model_dir), device=device)
    try:
        device_used = str(model.device)
        gpu_scores = np.asarray(model.predict(pairs), dtype=np.float64)
    finally:
        del model
        _release(device)

    cpu_model = CrossEncoder(str(model_dir), device="cpu")
    try:
        cpu_scores = np.asarray(cpu_model.predict(pairs), dtype=np.float64)
    finally:
        del cpu_model
        _release("cpu")

    finite = bool(np.isfinite(gpu_scores).all())
    max_diff = float(np.max(np.abs(gpu_scores - cpu_scores)))
    parity_passed = max_diff <= RERANKER_MAX_ABS_DIFF
    shape_ok = gpu_scores.shape == (len(pairs),)
    device_ok = device_used.startswith(device) if device != "cpu" else True
    return ModelSmokeResult(
        model=name,
        device_requested=device,
        device_used=device_used,
        output_shape=tuple(gpu_scores.shape),
        finite=finite,
        parity_metric=max_diff,
        parity_passed=parity_passed,
        passed=finite and parity_passed and shape_ok and device_ok,
    )
