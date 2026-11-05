"""P9a isolation: the benchmark stays off the answer path, and its optional libraries are loaded only by a baseline that
runs (ARCHITECTURE §18, §18.6, D95). Each check runs in a fresh interpreter, so earlier imports cannot hide a result."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app"
OPTIONAL_TOP_LEVEL = ("numpy", "scipy", "sklearn")


def _loaded_by(code: str) -> list[str]:
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return ast.literal_eval(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("module", ["app.decision", "app.evaluation", "app.retrieval", "app.storage", "app.benchmark"])
def test_importing_a_module_loads_no_optional_library(module):
    code = (
        "import importlib, sys\n"
        f"importlib.import_module({module!r})\n"
        f"print(sorted(name for name in sys.modules if name.split('.')[0] in {OPTIONAL_TOP_LEVEL!r}))\n"
    )
    assert _loaded_by(code) == []


def test_no_module_outside_the_benchmark_package_imports_it():
    offenders = {}
    for path in sorted(APP.rglob("*.py")):
        if path.relative_to(APP).parts[0] == "benchmark":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            if any(name == "app.benchmark" or name.startswith("app.benchmark.") for name in names):
                offenders[str(path.relative_to(REPO))] = names
    assert not offenders, offenders


def test_the_benchmark_package_imports_no_optional_library_at_module_level():
    for path in sorted((APP / "benchmark").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            top = {name.split(".")[0] for name in names}
            assert not top & set(OPTIONAL_TOP_LEVEL), f"{path.name} imports {sorted(top & set(OPTIONAL_TOP_LEVEL))}"
