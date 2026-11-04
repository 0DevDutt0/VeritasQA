"""P0-CLEAN exit criteria: the V1 dependency rule holds in every file that declares or imports code.

Denied names (D17; Q6 for spaCy, NLTK and rapidfuzz): no requirement file and no pyproject.toml
dependency may name PyTorch, a sentence-transformer or other embedding stack, a vector database, an
LLM SDK, spaCy, NLTK or rapidfuzz. No module under app/ may import them, and importing the whole
package must not load them. The lock file must carry every declared pin at the same version.

Run:  pytest tests/unit/test_p0_dependencies.py -q
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"
REQUIREMENT_FILES = ("requirements.txt", "requirements-experimental.txt", "requirements-validated.txt")

# Distributions that V1 must not declare.
DENIED_DISTRIBUTIONS = frozenset(
    {
        "torch",
        "torchvision",
        "torchaudio",
        "sentence-transformers",
        "transformers",
        "huggingface-hub",
        "tokenizers",
        "safetensors",
        "faiss",
        "faiss-cpu",
        "faiss-gpu",
        "chromadb",
        "openai",
        "anthropic",
        "spacy",
        "nltk",
        "rapidfuzz",
    }
)

# Top-level import names that app/ must never reach (the import names of the distributions above).
DENIED_MODULES = frozenset(
    {
        "torch",
        "torchvision",
        "torchaudio",
        "sentence_transformers",
        "transformers",
        "huggingface_hub",
        "tokenizers",
        "safetensors",
        "faiss",
        "chromadb",
        "openai",
        "anthropic",
        "spacy",
        "nltk",
        "rapidfuzz",
    }
)

_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)$")


def normalize(name: str) -> str:
    """PEP 503 name normalization: case-insensitive, with runs of -, _ and . treated as one -."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(spec: str) -> str | None:
    match = _NAME.match(spec)
    return normalize(match.group(1)) if match else None


def requirement_lines(path: Path) -> list[str]:
    """Requirement specs in a pip file. Comments, blank lines and option lines (-r, --index-url) are skipped."""
    specs = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            specs.append(line)
    return specs


def pins(path: Path) -> dict[str, str]:
    """Exact pins (name==version) in a pip file, keyed by normalized name."""
    result: dict[str, str] = {}
    for spec in requirement_lines(path):
        match = _PIN.match(spec)
        if match:
            result[normalize(match.group(1))] = match.group(2)
    return result


def _pyproject_specs() -> list[str]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    specs = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    return specs


def _imported_top_level_names(source: str) -> set[str]:
    """Every top-level module named by an import statement, including imports inside functions."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("filename", REQUIREMENT_FILES)
def test_requirement_file_names_no_denied_distribution(filename):
    path = REPO_ROOT / filename
    assert path.is_file(), f"{filename} is missing"
    named = {requirement_name(spec) for spec in requirement_lines(path)}
    assert not (named & DENIED_DISTRIBUTIONS), f"{filename} names {sorted(named & DENIED_DISTRIBUTIONS)}"


def test_pyproject_dependencies_name_no_denied_distribution():
    named = {requirement_name(spec) for spec in _pyproject_specs()}
    assert named, "pyproject.toml declares no dependencies"
    assert not (named & DENIED_DISTRIBUTIONS), f"pyproject.toml names {sorted(named & DENIED_DISTRIBUTIONS)}"


def test_baseline_requirements_exclude_the_optional_group():
    baseline = set(pins(REPO_ROOT / "requirements.txt"))
    assert "pymupdf" in baseline, "requirements.txt is missing its baseline pins"
    assert not ({"numpy", "scikit-learn"} & baseline), "the optional group leaked into requirements.txt"


def test_lock_carries_every_declared_pin_at_the_same_version():
    declared: dict[str, str] = {}
    for name in ("requirements.txt", "requirements-experimental.txt"):
        declared.update(pins(REPO_ROOT / name))
    assert declared, "no declared pins found"
    lock = pins(REPO_ROOT / "requirements-validated.txt")
    mismatched = {name: (version, lock.get(name)) for name, version in declared.items() if lock.get(name) != version}
    assert not mismatched, f"lock differs from the declared pins (declared, locked): {mismatched}"


def test_scanner_sees_imports_inside_functions():
    assert "torch" in _imported_top_level_names("def load():\n    import torch\n")
    assert "nltk" in _imported_top_level_names("from nltk.tokenize import sent_tokenize\n")
    assert _imported_top_level_names("from app.common import files\n") == {"app"}


def test_app_source_imports_no_denied_module():
    files = sorted(APP_DIR.rglob("*.py"))
    assert files, "app/ has no Python modules to check"
    offenders = {}
    for path in files:
        found = _imported_top_level_names(path.read_text(encoding="utf-8")) & DENIED_MODULES
        if found:
            offenders[str(path.relative_to(REPO_ROOT))] = sorted(found)
    assert not offenders, f"app/ imports denied modules: {offenders}"


def test_importing_every_app_module_loads_no_denied_module():
    code = (
        "import importlib, pkgutil, sys, app\n"
        "for info in pkgutil.walk_packages(app.__path__, 'app.'):\n"
        "    importlib.import_module(info.name)\n"
        "print(sorted({name.split('.')[0] for name in sys.modules}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    loaded = set(ast.literal_eval(result.stdout.strip().splitlines()[-1]))
    assert not (loaded & DENIED_MODULES), f"importing app/ loaded {sorted(loaded & DENIED_MODULES)}"
