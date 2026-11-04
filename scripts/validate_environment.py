"""Validate the VeritasQA environment (P0-ENV). Run it with the project interpreter:

    VeritasQA\\Scripts\\python.exe scripts\\validate_environment.py

Exit status: 0 when every baseline check passes, 1 when a baseline check fails, 2 when the
interpreter is not a virtual environment. Optional groups (GPU, experimental) are reported as
installed or not installed; they are not required for the baseline.
"""

from __future__ import annotations

import io
import os
import sys
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
os.environ["NLTK_DATA"] = os.pathsep.join(
    p for p in (str(REPO_ROOT / "models" / "nltk_data"), os.environ.get("NLTK_DATA", "")) if p
)

# Distribution names differ from import names for some pins in requirements.txt.
DISTRIBUTION_NAMES = {"pymupdf": "PyMuPDF"}
OPTIONAL_PACKAGES = (
    ("torch", "torch"),
    ("numpy", "numpy"),
    ("scikit-learn", "sklearn"),
    ("sentence-transformers", "sentence_transformers"),
    ("spacy", "spacy"),
    ("nltk", "nltk"),
    ("rapidfuzz", "rapidfuzz"),
)


def _line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))


def _pinned_baseline() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            pins[name.strip().lower()] = version.strip()
    return pins


def check_interpreter() -> bool:
    in_venv = sys.prefix != sys.base_prefix
    _line("INFO", "interpreter", sys.executable)
    _line("INFO", "python version", sys.version.split()[0])
    _line("INFO", "sys.prefix", sys.prefix)
    _line("INFO", "sys.base_prefix", sys.base_prefix)
    _line("INFO", "pip", metadata.version("pip"))
    _line("PASS" if in_venv else "FAIL", "running inside a virtual environment", str(in_venv))
    return in_venv


def check_baseline_pins() -> bool:
    ok = True
    for name, pinned in _pinned_baseline().items():
        dist = DISTRIBUTION_NAMES.get(name, name)
        try:
            installed = metadata.version(dist)
        except metadata.PackageNotFoundError:
            installed = "not installed"
        matches = installed == pinned
        ok &= matches
        _line("PASS" if matches else "FAIL", f"baseline pin {name}", f"pinned {pinned}, installed {installed}")
    return ok


def check_baseline_imports() -> bool:
    ok = True
    for module in ("fitz", "pdfplumber", "pydantic", "pytest"):
        try:
            __import__(module)
            _line("PASS", f"import {module}")
        except ImportError as exc:
            ok = False
            _line("FAIL", f"import {module}", str(exc))
    return ok


def check_fts5() -> bool:
    import sqlite3

    from app.storage import fts5

    try:
        version = fts5.ensure_fts5_available()
    except Exception as exc:  # StorageError or sqlite failure: both fail the check
        _line("FAIL", "SQLite FTS5 probe", str(exc))
        return False
    _line("PASS", "SQLite FTS5 probe (phrase and bm25)", f"sqlite {version} (module {sqlite3.sqlite_version})")
    return True


def check_pdf_round_trip() -> bool:
    """Create a synthetic PDF in memory and read it back with PyMuPDF and pdfplumber."""
    import fitz
    import pdfplumber

    marker = "Synthetic clause: the warranty lasts 24 months."
    try:
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), marker)
        data = document.tobytes()
        document.close()

        with fitz.open(stream=data, filetype="pdf") as reopened:
            pymupdf_text = reopened[0].get_text()
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            plumber_text = pdf.pages[0].extract_text() or ""
    except Exception as exc:
        _line("FAIL", "PDF round trip (synthetic document)", str(exc))
        return False
    ok = "24 months" in pymupdf_text and "24 months" in plumber_text
    _line(
        "PASS" if ok else "FAIL",
        "PDF round trip (synthetic document, PyMuPDF and pdfplumber)",
        f"fitz {fitz.VersionBind}, pdfplumber {metadata.version('pdfplumber')}",
    )
    return ok


def report_optional_packages() -> None:
    for dist, module in OPTIONAL_PACKAGES:
        try:
            version = metadata.version(dist)
        except metadata.PackageNotFoundError:
            _line("INFO", f"optional {dist}", "not installed")
            continue
        extra = ""
        if module == "torch":
            import torch

            extra = f" (CUDA build {torch.version.cuda}, cuda available {torch.cuda.is_available()})"
        _line("INFO", f"optional {dist}", version + extra)
    try:
        import spacy

        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
        sentences = [s.text for s in nlp("First sentence. Second sentence.").sents]
        _line("PASS" if len(sentences) == 2 else "FAIL", "optional spaCy blank('en') + sentencizer", str(sentences))
    except ImportError:
        pass
    try:
        from nltk.tokenize import sent_tokenize

        sent_tokenize("First sentence. Second sentence.", language="english")
        _line("PASS", "optional NLTK punkt_tab resource")
    except ImportError:
        pass
    except LookupError as exc:
        _line("INFO", "optional NLTK punkt_tab resource", f"missing ({exc.__class__.__name__}); see docs/SETUP.md")


def report_device() -> None:
    from app.common.device import ENV_VAR, DeviceConfigError, DeviceUnavailableError, resolve_device

    try:
        _line("INFO", f"{ENV_VAR} resolves to", resolve_device())
    except (DeviceConfigError, DeviceUnavailableError) as exc:
        _line("INFO", f"{ENV_VAR} resolution", str(exc))


def main() -> int:
    print("VeritasQA environment validation (P0-ENV)")
    print(f"repository: {REPO_ROOT}")
    if not check_interpreter():
        print("RESULT: not a virtual environment. Use the project venv (VeritasQA\\Scripts\\python.exe).")
        return 2
    results = [check_baseline_pins(), check_baseline_imports(), check_fts5(), check_pdf_round_trip()]
    report_optional_packages()
    report_device()
    ok = all(results)
    print("RESULT:", "baseline valid" if ok else "baseline has failures")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
