"""Device selection and CUDA checks for the optional GPU components (P0-ENV).

The baseline pipeline (PDF extraction, SQLite FTS5/BM25, extractive selection and verification)
runs on the CPU and never imports this module. The module serves the optional neural components
that SPEC §4 allows to be benchmarked later.

Rules:
- ``VERITASQA_DEVICE`` is read from ``os.environ`` only. No ``.env`` file is loaded.
- ``auto`` is the default. It is also used when the variable is unset or empty. It selects
  ``cuda`` when a CUDA device is usable and ``cpu`` otherwise.
- ``cuda`` never falls back silently. It raises ``DeviceUnavailableError`` with the reason.
- ``cpu`` always selects the CPU.
- Any other value raises ``DeviceConfigError``. It is not treated as ``auto``.
- PyTorch is imported only when a probe runs, so importing this module never requires it.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from app.common.errors import VeritasQAError

ENV_VAR = "VERITASQA_DEVICE"
DEVICE_MODES = ("auto", "cuda", "cpu")

# Relative tolerance for the CPU/GPU matmul comparison. float32 accumulation over 2048-term dot
# products differs from the CPU result by about 1e-6 relative. 1e-4 leaves margin and still
# catches a wrong result.
MATMUL_RELATIVE_TOLERANCE = 1e-4


class DeviceConfigError(VeritasQAError):
    """``VERITASQA_DEVICE`` holds a value other than auto, cuda or cpu."""


class DeviceUnavailableError(VeritasQAError):
    """CUDA was required, but it cannot be used on this machine."""


@dataclass(frozen=True)
class CudaProbe:
    """Result of asking PyTorch whether CUDA can be used. ``reason`` explains a negative result."""

    available: bool
    reason: str


@dataclass(frozen=True)
class GpuReport:
    """Facts about the active CUDA device, as reported by PyTorch."""

    device_name: str
    capability: tuple[int, int]
    arch_list: tuple[str, ...]
    total_memory_mib: float
    free_memory_mib: float
    torch_version: str
    torch_cuda_build: str | None


@dataclass(frozen=True)
class MatmulSmokeResult:
    """Outcome of one float32 matmul run on the GPU and compared with the CPU."""

    device_name: str
    size: int
    max_abs_error: float
    relative_error: float
    passed: bool


def probe_cuda() -> CudaProbe:
    """Report whether PyTorch can use a CUDA device here, and why it cannot when it cannot."""
    try:
        import torch
    except ImportError as exc:
        return CudaProbe(False, f"PyTorch is not installed ({exc})")
    except OSError as exc:  # On Windows a broken native library surfaces as OSError on import.
        return CudaProbe(False, f"PyTorch could not load its native libraries ({exc})")
    if not torch.cuda.is_available():
        return CudaProbe(
            False,
            f"torch {torch.__version__} (CUDA build {torch.version.cuda}) found no usable CUDA device",
        )
    return CudaProbe(True, f"CUDA device {torch.cuda.get_device_name(0)}")


def resolve_device(
    requested: str | None = None,
    *,
    probe: Callable[[], CudaProbe] = probe_cuda,
) -> str:
    """Return ``"cuda"`` or ``"cpu"``.

    ``requested`` overrides the environment. ``None`` reads ``VERITASQA_DEVICE``.
    """
    raw = os.environ.get(ENV_VAR) if requested is None else requested
    mode = (raw or "").strip().lower() or "auto"
    if mode not in DEVICE_MODES:
        raise DeviceConfigError(f"{ENV_VAR}={raw!r} is not valid. Use one of: auto, cuda, cpu.")
    if mode == "cpu":
        return "cpu"
    result = probe()
    if result.available:
        return "cuda"
    if mode == "cuda":
        raise DeviceUnavailableError(
            f"{ENV_VAR}=cuda, but CUDA is not usable: {result.reason}. "
            "Install the GPU group in this environment (pip install -r requirements-gpu.txt), "
            "check that nvidia-smi reports the GPU, or set VERITASQA_DEVICE=auto or cpu. "
            "docs/SETUP.md lists the tested combinations."
        )
    return "cpu"


def gpu_report() -> GpuReport:
    """Describe the active CUDA device. Raises ``DeviceUnavailableError`` when CUDA is not usable."""
    probe = probe_cuda()
    if not probe.available:
        raise DeviceUnavailableError(f"CUDA is not usable: {probe.reason}")
    import torch

    index = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(index)
    free_bytes, total_bytes = torch.cuda.mem_get_info(index)
    return GpuReport(
        device_name=props.name,
        capability=(props.major, props.minor),
        arch_list=tuple(torch.cuda.get_arch_list()),
        total_memory_mib=total_bytes / 2**20,
        free_memory_mib=free_bytes / 2**20,
        torch_version=torch.__version__,
        torch_cuda_build=torch.version.cuda,
    )


def cuda_matmul_smoke_test(size: int = 2048, seed: int = 0) -> MatmulSmokeResult:
    """Run a float32 matmul on the GPU, synchronize, copy the result back and compare with the CPU.

    ``torch.cuda.is_available()`` alone proves nothing about kernels, so this runs one.
    TF32 is disabled for the duration of the test so the comparison is full float32.
    """
    probe = probe_cuda()
    if not probe.available:
        raise DeviceUnavailableError(f"CUDA is not usable: {probe.reason}")
    import torch

    previous_tf32 = torch.backends.cuda.matmul.allow_tf32
    torch.backends.cuda.matmul.allow_tf32 = False
    try:
        generator = torch.Generator().manual_seed(seed)
        a = torch.randn(size, size, generator=generator, dtype=torch.float32)
        b = torch.randn(size, size, generator=generator, dtype=torch.float32)
        reference = a @ b  # CPU result

        product = a.to("cuda") @ b.to("cuda")
        if product.device.type != "cuda":
            raise RuntimeError("matmul did not run on the CUDA device")
        torch.cuda.synchronize()
        result = product.cpu()  # copy back to host; the device result is now retrieved
    finally:
        torch.backends.cuda.matmul.allow_tf32 = previous_tf32

    finite = bool(torch.isfinite(result).all())
    max_abs_error = float((result - reference).abs().max())
    scale = float(reference.abs().max())
    relative_error = max_abs_error / scale if scale > 0 else float("inf")
    return MatmulSmokeResult(
        device_name=torch.cuda.get_device_name(0),
        size=size,
        max_abs_error=max_abs_error,
        relative_error=relative_error,
        passed=finite and relative_error <= MATMUL_RELATIVE_TOLERANCE,
    )
