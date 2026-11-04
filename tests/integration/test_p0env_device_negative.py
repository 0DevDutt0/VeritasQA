"""P0-ENV: the no-usable-CUDA branch with a real PyTorch installation.

The unit tests inject the CUDA probe. These tests run in a subprocess with CUDA hidden
(CUDA_VISIBLE_DEVICES=-1). PyTorch then imports and reports no usable device, which is the branch a
broken NVIDIA driver takes. The tests skip when PyTorch is not installed. They need no GPU.

Run:  pytest tests/integration/test_p0env_device_negative.py -q
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="PyTorch is not installed"),
]


def _resolve_with_cuda_hidden(mode: str) -> str:
    """Run resolve_device() in a fresh interpreter with CUDA hidden and VERITASQA_DEVICE set."""
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "-1", "VERITASQA_DEVICE": mode}
    code = (
        "from app.common.device import resolve_device\n"
        "try:\n"
        "    print('resolved', resolve_device())\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__, str(exc))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    return result.stdout.strip()


def test_explicit_cuda_fails_with_actionable_error_when_torch_has_no_usable_device():
    output = _resolve_with_cuda_hidden("cuda")
    assert output.startswith("DeviceUnavailableError "), output
    assert "found no usable CUDA device" in output  # the reason
    assert "(CUDA build " in output  # torch's CUDA build is reported
    assert "requirements-gpu.txt" in output  # the next action
    assert "VERITASQA_DEVICE=auto or cpu" in output  # the explicit fallback


def test_auto_and_cpu_resolve_to_cpu_when_torch_has_no_usable_device():
    assert _resolve_with_cuda_hidden("auto") == "resolved cpu"
    assert _resolve_with_cuda_hidden("cpu") == "resolved cpu"


def test_invalid_value_is_rejected_even_when_cuda_is_hidden():
    assert _resolve_with_cuda_hidden("bogus").startswith("DeviceConfigError "), "bogus must not fall back"
