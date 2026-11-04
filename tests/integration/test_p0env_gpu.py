"""P0-ENV: CUDA checks that run real kernels on this machine.

Skipped automatically when no CUDA device is usable (conftest.py). A passing ``is_available()``
alone is not accepted as evidence: the matmul test below runs a kernel and compares the result.

Run:  pytest tests/integration/test_p0env_gpu.py -q
"""

from __future__ import annotations

import pytest

from app.common.device import cuda_matmul_smoke_test, gpu_report, resolve_device

pytestmark = [pytest.mark.integration, pytest.mark.requires_cuda]


def test_build_contains_kernels_for_this_gpu():
    report = gpu_report()
    major, minor = report.capability
    # The wheel must include machine code for this compute capability (sm_120 on an RTX 5090).
    assert f"sm_{major}{minor}" in report.arch_list, report
    assert report.total_memory_mib > 0
    assert 0 < report.free_memory_mib <= report.total_memory_mib


def test_gpu_matmul_matches_cpu_within_tolerance():
    result = cuda_matmul_smoke_test()
    assert result.passed, result
    assert result.relative_error <= 1e-4


def test_device_resolution_selects_cuda_on_this_machine(monkeypatch):
    monkeypatch.delenv("VERITASQA_DEVICE", raising=False)
    assert resolve_device() == "cuda"
    assert resolve_device("cuda") == "cuda"
