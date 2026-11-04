"""Validate the CUDA setup with real GPU work (P0-ENV). Run it with the project interpreter:

    VeritasQA\\Scripts\\python.exe scripts\\validate_gpu.py

Checks: PyTorch and CUDA build, device name and compute capability, whether the wheel contains
kernels for that capability, free and total memory, a float32 matmul on the GPU compared with the
CPU, and what VERITASQA_DEVICE resolves to.

Exit status: 0 when every check passes, 1 when a check fails, 2 when this is not a virtual
environment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))


def main() -> int:
    print("VeritasQA GPU validation (P0-ENV)")
    if sys.prefix == sys.base_prefix:
        print("RESULT: not a virtual environment. Use the project venv.")
        return 2

    import torch

    from app.common.device import (
        ENV_VAR,
        DeviceConfigError,
        DeviceUnavailableError,
        cuda_matmul_smoke_test,
        gpu_report,
        resolve_device,
    )

    _line("INFO", "torch", torch.__version__)
    _line("INFO", "torch CUDA build", str(torch.version.cuda))
    _line("INFO", "python", sys.version.split()[0])

    try:
        report = gpu_report()
    except DeviceUnavailableError as exc:
        _line("FAIL", "CUDA device", str(exc))
        print("RESULT: CUDA is not usable. See docs/SETUP.md for the tested driver and wheel combinations.")
        return 1

    major, minor = report.capability
    arch_tag = f"sm_{major}{minor}"
    arch_ok = arch_tag in report.arch_list
    _line("INFO", "GPU", report.device_name)
    _line("INFO", "compute capability", f"{major}.{minor} ({arch_tag})")
    _line("PASS" if arch_ok else "FAIL", "wheel contains kernels for this GPU", f"{arch_tag} in {list(report.arch_list)}")
    _line("INFO", "memory (total / free at start)", f"{report.total_memory_mib:.0f} MiB / {report.free_memory_mib:.0f} MiB")

    smoke = cuda_matmul_smoke_test()
    _line(
        "PASS" if smoke.passed else "FAIL",
        f"float32 matmul {smoke.size}x{smoke.size} on GPU vs CPU",
        f"relative error {smoke.relative_error:.3e} (tolerance 1.0e-04), max abs error {smoke.max_abs_error:.3e}",
    )

    try:
        resolved = resolve_device()
        _line("INFO", f"{ENV_VAR} resolves to", f"{resolved} (value: {os.environ.get(ENV_VAR, 'unset')})")
    except DeviceConfigError as exc:
        _line("FAIL", f"{ENV_VAR} value", str(exc))
        return 1

    ok = arch_ok and smoke.passed
    print("RESULT:", "GPU validated" if ok else "GPU validation failed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
