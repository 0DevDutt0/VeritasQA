"""Validate the downloaded model artifacts (P0-ENV). Run it with the project interpreter:

    VeritasQA\\Scripts\\python.exe scripts\\validate_models.py

Step 1: every local file must match the digest recorded in its manifest, and the model must be a
non-generative encoder or classifier.
Step 2: each model is loaded from its local directory with the Hub offline, run on CUDA with fixed
probe inputs, and compared with a CPU run of the same model. Free VRAM is printed before and
after each model so the memory released between models is visible.

Exit status: 0 when every check passes, 1 when a check fails, 2 when this is not a virtual
environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = REPO_ROOT / "models" / "manifests"
sys.path.insert(0, str(REPO_ROOT))


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))


def _free_mib() -> float:
    import torch

    free_bytes, _total = torch.cuda.mem_get_info(torch.cuda.current_device())
    return free_bytes / 2**20


def main() -> int:
    print("VeritasQA model validation (P0-ENV)")
    if sys.prefix == sys.base_prefix:
        print("RESULT: not a virtual environment. Use the project venv (VeritasQA\\Scripts\\python.exe).")
        return 2

    from app.common.device import DeviceUnavailableError, resolve_device
    from app.common.models import (
        load_manifest,
        smoke_test_embedder,
        smoke_test_reranker,
        verify_manifest,
    )

    manifest_paths = sorted(MANIFEST_DIR.glob("*.json"))
    if not manifest_paths:
        print("RESULT: no manifests found. Run scripts/download_models.py first.")
        return 1

    failures = 0
    manifests = [(path, load_manifest(path)) for path in manifest_paths]
    print("Step 1: local files against manifests")
    for path, manifest in manifests:
        problems = verify_manifest(manifest, REPO_ROOT)
        if problems:
            failures += 1
            for problem in problems:
                _line("FAIL", path.name, problem)
        else:
            _line(
                "PASS",
                f"{manifest['name']} ({manifest['repo_id']} @ {manifest['revision'][:12]})",
                f"{len(manifest['files'])} files match; generative={manifest['generative']}; "
                f"architectures={manifest['architectures']}; pipeline={manifest['pipeline_tag']}; "
                f"licence={manifest['license']}",
            )

    print("Step 2: load each model from its local directory and run it on CUDA")
    try:
        device = resolve_device("cuda")
    except DeviceUnavailableError as exc:
        print(f"[FAIL] CUDA: {exc}")
        print("RESULT: model inference cannot be validated without CUDA.")
        return 1

    for path, manifest in manifests:
        model_dir = REPO_ROOT / manifest["local_dir"]
        role = manifest["role"]
        free_before = _free_mib()
        if role == "embedding":
            result = smoke_test_embedder(model_dir, device, name=manifest["name"])
            metric = f"min cosine vs CPU {result.parity_metric:.6f} (need >= 0.999)"
        elif role == "reranker":
            result = smoke_test_reranker(model_dir, device, name=manifest["name"])
            metric = f"max |score GPU - CPU| {result.parity_metric:.2e} (need <= 1e-3)"
        else:
            failures += 1
            _line("FAIL", manifest["name"], f"unknown role {role!r}")
            continue
        free_after = _free_mib()
        status = "PASS" if result.passed else "FAIL"
        failures += 0 if result.passed else 1
        _line(
            status,
            f"{result.model} ({role}) on {result.device_used}",
            f"output shape {result.output_shape}; finite {result.finite}; {metric}; "
            f"VRAM free before {free_before:.0f} MiB, after {free_after:.0f} MiB",
        )

    print("RESULT:", "all model checks passed" if failures == 0 else f"{failures} check(s) failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
