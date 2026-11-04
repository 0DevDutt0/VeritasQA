"""P0-ENV: VERITASQA_DEVICE resolution and the lazy PyTorch import. CPU-only; no PyTorch needed.

The CUDA probe is injected, so these tests run the same way with or without the GPU group.

Run:  pytest tests/unit/test_p0env_device.py -q
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.common.device import (
    ENV_VAR,
    CudaProbe,
    DeviceConfigError,
    DeviceUnavailableError,
    probe_cuda,
    resolve_device,
)
from app.common.errors import VeritasQAError

REPO_ROOT = Path(__file__).resolve().parents[2]


class _Probe:
    """Counts calls and returns a fixed answer, so tests can also prove the probe was not needed."""

    def __init__(self, available: bool, reason: str = "fake probe") -> None:
        self.result = CudaProbe(available, reason)
        self.calls = 0

    def __call__(self) -> CudaProbe:
        self.calls += 1
        return self.result


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


def test_error_hierarchy():
    assert issubclass(DeviceConfigError, VeritasQAError)
    assert issubclass(DeviceUnavailableError, VeritasQAError)


def test_unset_variable_means_auto():
    assert resolve_device(probe=_Probe(True)) == "cuda"
    assert resolve_device(probe=_Probe(False)) == "cpu"


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_variable_means_auto(monkeypatch, value):
    monkeypatch.setenv(ENV_VAR, value)
    assert resolve_device(probe=_Probe(True)) == "cuda"
    assert resolve_device(probe=_Probe(False)) == "cpu"


def test_cpu_mode_never_consults_the_gpu(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "cpu")
    probe = _Probe(True)
    assert resolve_device(probe=probe) == "cpu"
    assert probe.calls == 0


def test_explicit_cuda_selects_cuda_when_usable(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "cuda")
    assert resolve_device(probe=_Probe(True)) == "cuda"


def test_explicit_cuda_fails_loudly_when_unusable(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "cuda")
    with pytest.raises(DeviceUnavailableError) as excinfo:
        resolve_device(probe=_Probe(False, reason="torch 2.14.1 found no usable CUDA device"))
    message = str(excinfo.value)
    assert "found no usable CUDA device" in message  # the reason is reported
    assert "requirements-gpu.txt" in message  # the next action is named
    assert "VERITASQA_DEVICE=auto" in message  # the fallback choice is named


def test_auto_falls_back_to_cpu_without_error(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "auto")
    assert resolve_device(probe=_Probe(False)) == "cpu"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("CUDA", "cuda"), ("  Cpu ", "cpu"), ("Auto", "cuda")],
)
def test_values_are_case_and_whitespace_insensitive(monkeypatch, value, expected):
    monkeypatch.setenv(ENV_VAR, value)
    assert resolve_device(probe=_Probe(True)) == expected


@pytest.mark.parametrize("value", ["gpu", "cuda:0", "0", "none", "tpu"])
def test_invalid_value_is_an_error_not_auto(monkeypatch, value):
    monkeypatch.setenv(ENV_VAR, value)
    with pytest.raises(DeviceConfigError, match="not valid"):
        resolve_device(probe=_Probe(True))
    with pytest.raises(DeviceConfigError):
        resolve_device(probe=_Probe(False))


def test_explicit_argument_overrides_environment(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "cpu")
    assert resolve_device("cuda", probe=_Probe(True)) == "cuda"


def test_missing_pytorch_is_reported_not_raised(monkeypatch):
    # Setting a module to None in sys.modules makes "import torch" raise ImportError.
    monkeypatch.setitem(sys.modules, "torch", None)
    probe = probe_cuda()
    assert probe.available is False
    assert "PyTorch is not installed" in probe.reason
    assert resolve_device("auto", probe=probe_cuda) == "cpu"
    with pytest.raises(DeviceUnavailableError, match="PyTorch is not installed"):
        resolve_device("cuda", probe=probe_cuda)


def test_importing_the_module_does_not_import_torch():
    code = "import sys, app.common.device; print('torch' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_module_reads_only_the_process_environment(monkeypatch, tmp_path):
    # No .env file is read: a .env in the working directory must have no effect.
    (tmp_path / ".env").write_text(f"{ENV_VAR}=cpu\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_device(probe=_Probe(True)) == "cuda"
