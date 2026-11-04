"""Shared pytest setup: skip markers for optional hardware and downloaded artifacts (P0-ENV).

- ``requires_cuda``: skipped unless PyTorch can use a CUDA device (see app/common/device.py).
- ``requires_models``: skipped unless models/manifests holds at least one manifest.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# NLTK data lives in the project (models/nltk_data), searched before any user-level location.
_NLTK_PROJECT_DIR = str(REPO_ROOT / "models" / "nltk_data")
os.environ["NLTK_DATA"] = os.pathsep.join(
    part for part in (_NLTK_PROJECT_DIR, os.environ.get("NLTK_DATA", "")) if part
)


def _cuda_skip_reason() -> str | None:
    from app.common.device import probe_cuda

    probe = probe_cuda()
    return None if probe.available else f"needs a usable CUDA device: {probe.reason}"


def _models_skip_reason() -> str | None:
    # Manifests are tracked in git, but the weights are not. Skip when a model directory is absent,
    # so a fresh clone reports the missing download instead of failing.
    from app.common.models import load_manifest

    manifest_paths = sorted((REPO_ROOT / "models" / "manifests").glob("*.json"))
    if not manifest_paths:
        return "needs model manifests under models/manifests (run scripts/download_models.py)"
    absent = [
        path.stem
        for path in manifest_paths
        if not (REPO_ROOT / load_manifest(path)["local_dir"]).is_dir()
    ]
    if absent:
        return f"needs local model files for {absent} (run scripts/download_models.py)"
    return None


_PROBES = {"requires_cuda": _cuda_skip_reason, "requires_models": _models_skip_reason}


def pytest_collection_modifyitems(config, items):
    reasons: dict[str, str | None] = {}
    for item in items:
        for marker, probe in _PROBES.items():
            if item.get_closest_marker(marker) is None:
                continue
            if marker not in reasons:  # probe each condition once per session
                reasons[marker] = probe()
            if reasons[marker]:
                item.add_marker(pytest.mark.skip(reason=reasons[marker]))
